import random

from locust import FastHttpUser, TaskSet, between

from testbed.loadgenerator.common import request


class TeaStoreBehavior(TaskSet):
    def on_start(self):
        self.requests_since_connection_recycle = 0
        self.user_id = f"user{random.randint(1, 99)}"
        request(self, "get", "/")
        request(self, "get", "/login")
        request(
            self,
            "post",
            "/loginAction",
            params={"username": self.user_id, "password": "password"},
        )

    def browse(self):
        category_id = random.randint(2, 6)
        page = random.randint(1, 5)
        request(
            self,
            "get",
            "/category",
            params={"page": page, "category": category_id},
        )
        product_id = random.randint(7, 506)
        request(self, "get", "/product", params={"id": product_id})

    def add_to_cart(self):
        product_id = random.randint(7, 506)
        request(self, "get", "/product", params={"id": product_id})
        request(
            self,
            "post",
            "/cartAction",
            params={"addToCart": "", "productid": product_id},
        )

    def checkout(self):
        self.add_to_cart()
        request(
            self,
            "post",
            "/cartAction",
            params={
                "firstname": "User",
                "lastname": "User",
                "adress1": "Road",
                "adress2": "City",
                "cardtype": "volvo",
                "cardnumber": "314159265359",
                "expirydate": "12/2050",
                "confirm": "Confirm",
            },
        )

    def profile(self):
        request(self, "get", "/profile")

    tasks = {
        browse: 10,
        add_to_cart: 2,
        checkout: 1,
        profile: 3,
    }


class WebsiteUser(FastHttpUser):
    tasks = [TeaStoreBehavior]
    wait_time = between(1, 10)


__all__ = ["WebsiteUser"]
