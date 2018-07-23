Django MongoDB Cash Backend
===========================

The only Django MongoDB Cache backend you need.

Installation and Usage
----------------------
Install with:

``pip install django-mongodb-cash-backend``

Add the following to your Django settings::

    CACHES = {
        'default': {
            'BACKEND': 'django_mongodb_cash_backend.MongoDBCache',
            "LOCATION": "hostname[:port]",
            "OPTIONS": {
                "USERNAME": "username_if_desired",
                "PASSWORD": "password_if_needed",
                "DATABASE": "cache_db_name",
                "COLLECTION": "cache_colleciton", # default: django_cache
            },
            "TIMEOUT": 86400, # either set TIMEOUT or MAX_ENTRIES, not both
            "MAX_ENTRIES": 10000, # either set MAX_ENTRIES or TIMEOUT, not both
        }
    }


Tips and hints
--------------

Django MongoDB cash backend will handle TTL index creation, or will create a capped collection if MAX_ENTRIES is set. You should ensure that the collections are not created beforehands, so that the backend can do its work correctly.
