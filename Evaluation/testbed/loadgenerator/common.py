import datetime
import os
import random

from faker import Faker
from locust import FastHttpUser, TaskSet, between

fake = Faker()

CONNECTION_RECYCLE_EVERY_REQUESTS = int(
    os.getenv("CONNECTION_RECYCLE_EVERY_REQUESTS", "50")
)
if CONNECTION_RECYCLE_EVERY_REQUESTS < 1:
    raise ValueError("CONNECTION_RECYCLE_EVERY_REQUESTS must be at least 1")

products = [
    "0PUK6V6EV0",
    "1YMWWN1N4O",
    "2ZYFJ3GM2N",
    "66VCHSJNUP",
    "6E92ZMYYFZ",
    "9SIQT8TOJO",
    "L9ECAV7KIM",
    "LS4PSXUNUM",
    "OLJCESPC7Z",
]


def request(l, method, path, *args, **kwargs):
    response = getattr(l.client, method)(path, *args, **kwargs)
    l.requests_since_connection_recycle += 1
    if l.requests_since_connection_recycle >= CONNECTION_RECYCLE_EVERY_REQUESTS:
        # FastHttpUser owns one connection pool per simulated user. Closing the
        # pool after a completed request preserves cookies, and the next request
        # establishes a connection that can be routed to any Ready endpoint.
        l.client.client.clientpool.close()
        l.requests_since_connection_recycle = 0
    return response


def index(l):
    request(l, "get", "/")


def setCurrency(l):
    currencies = ["EUR", "USD", "JPY", "CAD", "GBP", "TRY"]
    request(
        l,
        "post",
        "/setCurrency",
        {"currency_code": random.choice(currencies)},
    )


def browseProduct(l):
    request(l, "get", "/product/" + random.choice(products))


def viewCart(l):
    request(l, "get", "/cart")


def addToCart(l):
    product = random.choice(products)
    request(l, "get", "/product/" + product)
    request(
        l,
        "post",
        "/cart",
        {"product_id": product, "quantity": random.randint(1, 10)},
    )


def empty_cart(l):
    request(l, "post", "/cart/empty")


def checkout(l):
    addToCart(l)
    current_year = datetime.datetime.now().year + 1
    request(
        l,
        "post",
        "/cart/checkout",
        {
            "email": fake.email(),
            "street_address": fake.street_address(),
            "zip_code": fake.zipcode(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "country": fake.country(),
            "credit_card_number": fake.credit_card_number(card_type="visa"),
            "credit_card_expiration_month": random.randint(1, 12),
            "credit_card_expiration_year": random.randint(
                current_year, current_year + 70
            ),
            "credit_card_cvv": f"{random.randint(100, 999)}",
        },
    )


def logout(l):
    request(l, "get", "/logout")


class UserBehavior(TaskSet):
    def on_start(self):
        self.requests_since_connection_recycle = 0
        index(self)

    tasks = {
        index: 1,
        setCurrency: 2,
        browseProduct: 10,
        addToCart: 2,
        viewCart: 3,
        checkout: 1,
    }


class WebsiteUser(FastHttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 10)
