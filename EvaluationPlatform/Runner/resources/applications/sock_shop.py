import random

from locust import FastHttpUser, TaskSet, between, task
from locust.exception import RescheduleTask

from testbed.loadgenerator.common import request


class SockShopBehavior(TaskSet):
    def on_start(self):
        self.requests_since_connection_recycle = 0

    def checked_request(self, method, path, *, statuses=(200,), **kwargs):
        with request(self, method, path, catch_response=True, **kwargs) as response:
            if response.status_code not in statuses:
                response.failure(
                    f"Sock Shop HTTP failure: {path} ({response.status_code})"
                )
                raise RescheduleTask()
            return response

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

        self.checked_request("get", "/category.html")
        self.checked_request("get", "/detail.html", params={"id": product_id})
        self.checked_request(
            "post",
            "/cart",
            json={"id": product_id, "quantity": 1},
            statuses=(200, 201, 202),
        )
        self.checked_request("get", "/basket.html")
        self.checked_request("delete", "/cart", statuses=(200, 202))


class WebsiteUser(FastHttpUser):
    tasks = [SockShopBehavior]
    wait_time = between(1, 5)


__all__ = ["WebsiteUser"]
