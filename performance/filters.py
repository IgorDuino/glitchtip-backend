import re
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone
from django_filters import rest_framework as filters
from django_filters.fields import IsoDateTimeField

from projects.models import Project

from .models import TransactionGroup


RELATIVE_TIME_REGEX = re.compile(r"[nowmhd0-9\-]*$")


class RelativeIsoDateTimeField(IsoDateTimeField):
    """
    Allow relative terms like now or now-1h. Only 0 or 1 subtraction operation is permitted.

    Accepts
    - now
    - - (subtraction)
    - m (minutes)
    - h (hours)
    - d (days)
    """

    def strptime(self, value, format):
        # Check for relative time, if panic just assume it's a datetime
        if "now" in value and RELATIVE_TIME_REGEX.match(value):
            parts = [x.strip() for x in value.split("-")]
            if len(parts) > 0 and len(parts) < 3 and parts[0] == "now":
                result = timezone.now()
                if len(parts) > 1:
                    part = parts[0]
                    numbers = re.findall(r"\d+", part)
                    if numbers:
                        if part.endswith("m"):
                            result -= timedelta(minutes=numbers[0])
                        if part.endswith("h"):
                            result -= timedelta(hours=numbers[0])
                        if part.endswith("d"):
                            result -= timedelta(days=numbers[0])
                return result
        return super().strptime(value, format)


class RelativeIsoDateTimeFilter(filters.IsoDateTimeFilter):
    field_class = RelativeIsoDateTimeField


class TransactionGroupFilter(filters.FilterSet):
    start = RelativeIsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="gte",
        label="Transaction start date",
    )
    end = RelativeIsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="lte",
        label="Transaction end date",
    )
    project = filters.ModelMultipleChoiceFilter(queryset=Project.objects.all())
    query = filters.CharFilter(
        field_name="transaction",
        lookup_expr="icontains",
        label="Transaction text search",
    )

    class Meta:
        model = TransactionGroup
        fields = ["project", "start", "end"]

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        environments = self.request.query_params.getlist("environment")
        if environments:
            queryset = queryset.filter(tags__environment__has_any_keys=environments)

        # This annotation must be applied after any related transactionevent filter
        queryset = queryset.annotate(
            avg_duration=Avg("transactionevent__duration"),
            transaction_count=Count("transactionevent"),
        )

        return queryset
