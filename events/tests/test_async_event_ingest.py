from timeit import default_timer as timer
from rest_framework.test import APITestCase
from rest_framework import exceptions
from rest_framework.test import APIRequestFactory
from ..views import ABaseEventAPIView


class AsyncEventStoreTestCase(APITestCase):
    def test_auth_from_request(self):
        factory = APIRequestFactory()
        dsn = "00000000000000000000000000000000"
        data = {"glitchtip_key": dsn}

        get_request = factory.post("/api/1/store/")
        get_request.GET = data

        data = [{"dsn": f"https://{dsn}@app.glitchtip.com/1"}]
        post_request = factory.post("/api/1/store/", data, format="json")
        post_request.data = data

        data = {"HTTP_X_SENTRY_AUTH": "sentry sentry_key=" + dsn}
        header_request = factory.post("/api/1/store/", headers=data)
        header_request.data = {}
        header_request.META = data

        invalid_request = factory.post("/api/1/store/", headers={})
        invalid_request.data = {}

        self.assertEqual(ABaseEventAPIView.auth_from_request(get_request), dsn)
        self.assertEqual(ABaseEventAPIView.auth_from_request(post_request), dsn)
        self.assertEqual(ABaseEventAPIView.auth_from_request(header_request), dsn)
        with self.assertRaises(exceptions.NotAuthenticated):
            ABaseEventAPIView.auth_from_request(invalid_request)

        if False:
            for request in [get_request, header_request, post_request]:
                start = timer()
                for _ in range(1):
                    ABaseEventAPIView.auth_from_request(request)
                end = timer()
                print(end - start)
