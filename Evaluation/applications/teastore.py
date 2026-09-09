import random

from locust import FastHttpUser, TaskSet, between, task
from locust.exception import RescheduleTask

from testbed.loadgenerator.common import request


class TeaStoreBehavior(TaskSet):
    def on_start(self):
        self.requests_since_connection_recycle = 0

    def checked_request(self, method, path, *, expected_text=None, **kwargs):
        # Redirects can end on a successful HTTP page after a failed login or
        # rejected checkout. Count these as workload failures as well.
        with request(self, method, path, catch_response=True, **kwargs) as response:
            healthy = response.status_code == 200
            if healthy and expected_text and expected_text not in (response.text or ""):
                response.failure(f"TeaStore semantic check failed: {path}")
                healthy = False
            elif not healthy:
                response.failure(f"TeaStore HTTP failure: {path} ({response.status_code})")
        if not healthy:
            raise RescheduleTask()

    @task
    def shopping_session(self):
        # SessionBlob contains the cart itself. Keep sessions bounded even
        # when checkout fails, without hiding failed requests from Locust.
        self.client.cookiejar.clear()
        try:
            self.login()
            for _ in range(random.randint(1, 3)):
                self.browse()
                self.wait()
            self.add_to_cart()
            self.wait()
            self.checkout()
            self.profile()
            self.checked_request("post", "/loginAction", params={"logout": ""},
                                 expected_text="You are logged out!")
        finally:
            self.client.cookiejar.clear()

    def login(self):
        self.user_id = f"user{random.randint(1, 99)}"
        self.checked_request("get", "/")
        self.checked_request("get", "/login")
        self.checked_request(
            "post",
            "/loginAction",
            params={"username": self.user_id, "password": "password"},
            expected_text="You are logged in!",
        )

    def browse(self):
        category_id = random.randint(2, 6)
        page = random.randint(1, 5)
        self.checked_request(
            "get",
            "/category",
            params={"page": page, "category": category_id},
        )
        product_id = random.randint(7, 506)
        self.checked_request("get", "/product", params={"id": product_id})

    def add_to_cart(self):
        product_id = random.randint(7, 506)
        self.checked_request("get", "/product", params={"id": product_id})
        self.checked_request(
            "post",
            "/cartAction",
            params={"addToCart": "", "productid": product_id},
            expected_text=f"Product {product_id} is added to cart!",
        )

    def checkout(self):
        self.checked_request(
            "post",
            "/cartAction",
            params={
                "firstname": "User",
                "lastname": "User",
                "address1": "Road",
                "address2": "City",
                "cardtype": "volvo",
                "cardnumber": "314159265359",
                "expirydate": "12/2050",
                "confirm": "Confirm",
            },
            expected_text="Your order is confirmed!",
        )

    def profile(self):
        self.checked_request("get", "/profile")


class WebsiteUser(FastHttpUser):
    tasks = [TeaStoreBehavior]
    wait_time = between(1, 10)


__all__ = ["WebsiteUser"]
