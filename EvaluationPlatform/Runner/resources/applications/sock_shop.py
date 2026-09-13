import base64
import random
from uuid import uuid4

from locust import FastHttpUser, TaskSet, between, task
from locust.exception import RescheduleTask

from testbed.loadgenerator.common import request


class SockShopBehavior(TaskSet):
    def on_start(self):
        self.requests_since_connection_recycle = 0
        self.customer_registered = False
        self.address_ready = False
        self.card_ready = False
        self.username = "evaluation-" + uuid4().hex
        self.password = "evaluation-only"

    def checked_request(self, method, path, *, statuses=(200,), require_id=False, **kwargs):
        with request(self, method, path, catch_response=True, **kwargs) as response:
            if response.status_code not in statuses:
                response.failure(
                    f"Sock Shop HTTP failure: {path} ({response.status_code})"
                )
                raise RescheduleTask()
            if require_id:
                try:
                    body = response.json()
                    if not isinstance(body, dict) or not body.get("id"):
                        raise ValueError("missing id")
                except (TypeError, ValueError):
                    response.failure(f"Sock Shop invalid response: {path} (missing id)")
                    raise RescheduleTask() from None
            return response

    def prepare_customer(self):
        # Keep setup state across failed tasks, so dependency failures do not
        # trap an existing user in repeated duplicate registration attempts.
        if not self.customer_registered:
            self.checked_request("post", "/register", require_id=True, json={
                "username": self.username, "password": self.password,
                "email": self.username + "@example.invalid",
            })
            self.customer_registered = True
        authorization = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        self.checked_request("get", "/login", headers={"Authorization": "Basic " + authorization})
        if not self.address_ready:
            self.checked_request("post", "/addresses", require_id=True, json={
                "number": "1", "street": "Evaluation Street", "city": "Test City",
                "postcode": "00000", "country": "Test Country",
            })
            self.address_ready = True
        if not self.card_ready:
            self.checked_request("post", "/cards", require_id=True, json={
                "longNum": "1234567890123456", "expires": "12/99", "ccv": "123",
            })
            self.card_ready = True

    @task
    def shopping_session(self):
        self.checked_request("get", "/")
        with request(self, "get", "/catalogue", catch_response=True) as catalogue:
            if catalogue.status_code != 200:
                catalogue.failure(
                    f"Sock Shop HTTP failure: /catalogue ({catalogue.status_code})"
                )
                raise RescheduleTask()
            try:
                products = catalogue.json()
                product_id = random.choice(products)["id"]
            except (TypeError, ValueError, KeyError, IndexError):
                catalogue.failure("Sock Shop catalogue returned no usable products")
                raise RescheduleTask() from None

        self.prepare_customer()
        self.checked_request("get", "/category.html")
        self.checked_request("get", "/detail.html", params={"id": product_id})
        self.checked_request("delete", "/cart", statuses=(200, 202))
        self.checked_request(
            "post",
            "/cart",
            json={"id": product_id, "quantity": 1},
            statuses=(200, 201, 202),
        )
        self.checked_request("get", "/basket.html")
        self.checked_request("post", "/orders", statuses=(200, 201), require_id=True)
        self.checked_request("delete", "/cart", statuses=(200, 202))


class WebsiteUser(FastHttpUser):
    tasks = [SockShopBehavior]
    wait_time = between(1, 5)


__all__ = ["WebsiteUser"]
