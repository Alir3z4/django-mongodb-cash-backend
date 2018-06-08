> Forked from: https://github.com/Alir3z4/django-mongodb-cash-backend


Django MongoDB Cash Backend
===========================

The only Django MongoDB Cache backend you need.

Installation and Usage
----------------------
Install with:

``pip install django-mongodb-cash-backend``

Add the following to your Django settings:

    CACHES = {
        'default': {
            'BACKEND': 'django_mongodb_cash_backend.MongoDBCache',
            "LOCATION": "DEFAULT",
            "TIMEOUT": 86400,
            "OPTIONS": {
                "HOST": "MongoDB_host",
                "PORT": 12345,
                "USERNAME": "username_if_desired",
                "PASSWORD": "password_if_needed"
            },
        }
    }
