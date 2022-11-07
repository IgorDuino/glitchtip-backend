import json
import logging
import random
import string
import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db import connection
from django.db.models import Exists, OuterRef
from django.db.utils import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from sentry_sdk import capture_exception, set_context, set_level

from difs.models import DebugInformationFile
from difs.tasks import difs_run_resolve_stacktrace
from performance.serializers import TransactionEventSerializer
from projects.models import Project
from sentry.utils.auth import parse_auth_header

from .negotiation import IgnoreClientContentNegotiation
from .parsers import EnvelopeParser
from .serializers import (
    EnvelopeHeaderSerializer,
    StoreCSPReportSerializer,
    StoreDefaultSerializer,
    StoreErrorSerializer,
)

logger = logging.getLogger(__name__)


def test_event_view(request):
    """
    This view is used only to test event store performance
    It requires DEBUG to be True
    """
    factory = RequestFactory()
    request = request = factory.get(
        "/api/6/store/?sentry_key=244703e8083f4b16988c376ea46e9a08"
    )
    with open("events/test_data/py_hi_event.json") as json_file:
        data = json.load(json_file)
    data["event_id"] = uuid.uuid4()
    data["message"] = "".join(
        random.choices(string.ascii_uppercase + string.digits, k=8)
    )
    request.data = data
    EventStoreAPIView().post(request, id=6)

    return HttpResponse("<html><body></body></html>")


class BaseEventAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    content_negotiation_class = IgnoreClientContentNegotiation
    http_method_names = ["post"]

    @classmethod
    def auth_from_request(cls, request):
        # Accept both sentry or glitchtip prefix.
        # Prefer glitchtip when not using a sentry SDK but support both.
        result = {
            k: request.GET[k]
            for k in request.GET.keys()
            if k[:7] == "sentry_" or k[:10] == "glitchtip_"
        }

        if request.META.get("HTTP_X_SENTRY_AUTH", "")[:7].lower() == "sentry ":
            if result:
                raise SuspiciousOperation(
                    "Multiple authentication payloads were detected."
                )
            result = parse_auth_header(request.META["HTTP_X_SENTRY_AUTH"])
        elif request.META.get("HTTP_AUTHORIZATION", "")[:7].lower() == "sentry ":
            if result:
                raise SuspiciousOperation(
                    "Multiple authentication payloads were detected."
                )
            result = parse_auth_header(request.META["HTTP_AUTHORIZATION"])

        if not result:
            if (
                isinstance(request.data, list)
                and len(request.data)
                and "dsn" in request.data[0]
            ):
                dsn = urlparse(request.data[0]["dsn"])
                if username := dsn.username:
                    return username
            raise exceptions.NotAuthenticated(
                "Unable to find authentication information"
            )

        try:
            key = uuid.UUID(result.get("sentry_key", result.get("glitchtip_key")))
        except ValueError as err:
            raise exceptions.AuthenticationFailed("invalid api key", code=401) from err
        return key

    def event_preprocess(self, request, project_id):
        """
        Check auth, prefetch related data to be used after deserialization
        Use database function for optimization.
        Return context to be used with serializer
        """
        if settings.EVENT_STORE_DEBUG:
            print(json.dumps(request.data))

        sentry_key = BaseEventAPIView.auth_from_request(request)
        release = request.data.get("release")
        if release:
            release = release[:256]
        environment = request.data.get("environment")
        if environment:
            environment = environment[:256]
            if "/" in environment:
                environment = None
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM event_preprocess(%s, %s, %s, %s)",
                (project_id, sentry_key, release, environment),
            )
            result = cursor.fetchone()
        context = {
            "organization_id": result[0],
            "has_diffs": result[1],
            "is_accepting_events": result[2],
            "should_scrub_ip_addresses": result[3],
            "release_id": result[4],
            "environment_id": result[5],
            "project_id": project_id,
        }

        if not context["organization_id"]:
            raise exceptions.AuthenticationFailed({"error": "Invalid api key"})
        if not context["is_accepting_events"]:
            raise exceptions.Throttled(detail="event rejected due to rate limit")
        return context

    def get_event_serializer_class(self, data=None):
        """Determine event type and return serializer"""
        if data is None:
            data = []
        if "exception" in data and data["exception"]:
            return StoreErrorSerializer
        if "platform" not in data:
            return StoreCSPReportSerializer
        return StoreDefaultSerializer

    def process_event(self, data, context):
        """Determine correct serializer and save event"""
        set_context("incoming event", data)
        serializer = self.get_event_serializer_class(data)(
            data=data,
            context=context,
        )
        try:
            serializer.is_valid(raise_exception=True)
        except exceptions.ValidationError as err:
            set_level("warning")
            capture_exception(err)
            logger.warning("Invalid event %s", serializer.errors)
            return Response()
        event = serializer.save()
        if event.data.get("exception") is not None and context["has_diffs"]:
            difs_run_resolve_stacktrace(event.event_id)
        return Response({"id": event.event_id_hex})


class EventStoreAPIView(BaseEventAPIView):
    def post(self, request, *args, **kwargs):
        if settings.MAINTENANCE_EVENT_FREEZE:
            return Response(
                {
                    "message": "Events are not currently being accepted due to database maintenance."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        project_id = kwargs.get("id")
        try:
            context = self.event_preprocess(request, project_id)
        except exceptions.AuthenticationFailed as err:
            # Replace 403 status code with 401 to match OSS Sentry
            return Response(err.detail, status=401)
        context["request"] = request
        return self.process_event(request.data, context)


class CSPStoreAPIView(EventStoreAPIView):
    pass


class EnvelopeAPIView(BaseEventAPIView):
    parser_classes = [EnvelopeParser]

    def get_serializer_class(self):
        return TransactionEventSerializer

    def post(self, request, *args, **kwargs):
        if settings.MAINTENANCE_EVENT_FREEZE:
            return Response(
                {
                    "message": "Events are not currently being accepted due to database maintenance."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if settings.EVENT_STORE_DEBUG:
            print(json.dumps(request.data))
        project = self.get_project(request, kwargs.get("id"))

        data = request.data
        if len(data) < 2:
            logger.warning("Envelope has no headers %s", data)
            raise exceptions.ValidationError("Envelope has no headers")
        event_header_serializer = EnvelopeHeaderSerializer(data=data.pop(0))
        event_header_serializer.is_valid(raise_exception=True)
        # Multi part envelopes are not yet supported
        message_header = data.pop(0)
        if message_header.get("type") == "transaction":
            serializer = self.get_serializer_class()(
                data=data.pop(0), context={"request": self.request, "project": project}
            )
            try:
                serializer.is_valid(raise_exception=True)
            except exceptions.ValidationError as err:
                logger.warning("Invalid envelope payload", exc_info=True)
                raise err
            try:
                event = serializer.save()
            except IntegrityError as err:
                logger.warning("Duplicate event id", exc_info=True)
                raise exceptions.ValidationError("Duplicate event id") from err
            return Response({"id": event.event_id_hex})
        elif message_header.get("type") == "event":
            event_data = data.pop(0)
            return self.process_event(event_data, request, project)
        elif message_header.get("type") == "session":
            return Response(
                {"message": "Session events are not supported at this time."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        return Response(status=status.HTTP_501_NOT_IMPLEMENTED)
