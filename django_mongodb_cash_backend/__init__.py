# -*- coding: utf-8 -*-
# Author:
#  Karol Sikora <karol.sikora@laboratorium.ee>, (c) 2012
#  Alireza Savand <alireza.savand@gmail.com>, (c) 2013, 2014, 2015
#  Olivier Hoareau <olivier.p.hoareau@gmail.com>, (c) 2018

try:
    import cPickle as pickle
except ImportError:
    import pickle
import base64
import re
from datetime import datetime, timedelta
import functools

import pymongo
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.core.cache.backends.base import BaseCache, DEFAULT_TIMEOUT
from pymongo.errors import OperationFailure, ExecutionTimeout

def get_host_and_port(location):
    location = location or 'localhost:27017'
    split_value = location.split(':')
    if len(split_value) == 1:
        return split_value[0], 27017
    elif len(split_value) > 1:
        return split_value[0], split_value[1]
    else:
        return None, None


def reconnect(retries=3):
    def _decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            tries = 0
            while tries < retries:
                try:
                    return f(*args, **kwargs)
                except pymongo.errors.AutoReconnect:
                    tries += 1
            raise pymongo.errors.ConnectionFailure('Could not reconnect to mongodb after {} retries.'.format(retries))
        return wrapper
    return _decorator

    

class MongoDBCache(BaseCache):
    def __init__(self, location, params):
        options = params.get('OPTIONS', {})

        if not 'timeout' in params and not 'TIMEOUT' in params:
            params['TIMEOUT'] = None
        if not 'max_entries' in params and not 'MAX_ENTRIES' in options:
            options['MAX_ENTRIES'] = -1
        

        BaseCache.__init__(self, params)

        self._host, self._port = get_host_and_port(location)
        
        self._database = options.get('DATABASE', None)
        self._username = options.get('USERNAME') or None
        self._password = options.get('PASSWORD') or None

        self._collection_name = options.get('COLLECTION', None) or 'django_cache'

        if self._max_entries is not None and self._max_entries <= 0:
            self._max_entries = None

        if self.default_timeout is not None and self.default_timeout <= 0:
            self.default_timeout = None

        if self.default_timeout is not None and self._max_entries is not None:
            raise ImproperlyConfigured('MongoDBCache shall be configured either with TIMEOUT or MAX_ENTRIES, not both.')

        if self.default_timeout is None and self._max_entries is None:
            raise ImproperlyConfigured('MongoDBCache shall be configured with TIMEOUT or MAX_ENTRIES. Specify one or the other.')


    def make_key(self, key, version=None):
        """
        Additional regexp to remove $ and . characters,
        as they cause special behaviour in mongodb
        """
        key = super(MongoDBCache, self).make_key(key, version)

        return re.sub(r'\$|\.', '_', key)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)

        return self._base_set('add', key, value, timeout)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)

        return self._base_set('set', key, value, timeout)

    @reconnect()
    def _base_set(self, mode, key, value, timeout=DEFAULT_TIMEOUT):
        print self, mode, key, value, timeout
        if timeout is DEFAULT_TIMEOUT:
            timeout = self.default_timeout

        now = timezone.now()
        if timeout not in (None, -1):
            expires = now + timedelta(seconds=timeout)
        else:
            expires = None
        coll = self._get_collection()
        pickled = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
        encoded = base64.encodestring(pickled).strip()

        if mode == 'add' and self.has_key(key):
            return False

        try:
            coll.update_one(
                {'key':key},
                {'$set': {'data': encoded, 'expires': expires, 'last_change': now}},
                upsert = True,
            )
        #TODO: check threadsafety!
        except (OperationFailure, ExecutionTimeout), e:
            return False
        else:
            return True

    @reconnect()
    def get(self, key, default=None, version=None):
        coll = self._get_collection()
        key = self.make_key(key, version)
        self.validate_key(key)
        now = timezone.now()

        data = coll.find_one({
            '$and':
                [
                    {
                        'key': key
                    },
                    {'$or': [
                        {'expires': {'$gt': now}},
                        {'expires': None},
                    ]}
                ]
            })
        if not data:
            return default

        unencoded = base64.decodestring(data['data'])
        unpickled = pickle.loads(unencoded)

        return unpickled

    @reconnect()
    def get_many(self, keys, version=None):
        coll = self._get_collection()
        now = datetime.utcnow()
        out = {}
        parsed_keys = {}
        now = timezone.now()

        for key in keys:
            pkey = self.make_key(key, version)
            self.validate_key(pkey)
            parsed_keys[pkey] = key

        data = coll.find({
            '$and':
                [
                    {
                        'key': {'$in': parsed_keys.keys()}
                    },
                    {'$or': [
                        {'expires': {'$gt': now}},
                        {'expires': None},
                    ]}
                ]
            }
        )
        for result in data:
            unencoded = base64.decodestring(result['data'])
            unpickled = pickle.loads(unencoded)
            out[parsed_keys[result['key']]] = unpickled

        return out

    @reconnect()
    def delete(self, key, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)
        coll = self._get_collection()
        if not 'capped' in self._db.command("collstats", self._collection_name):
            coll.remove({'key': key})
        else:
            coll.update_one({'key': key}, {'$set':{'expires':timezone.now()}})

    @reconnect()
    def has_key(self, key, version=None):
        coll = self._get_collection()
        key = self.make_key(key, version)
        self.validate_key(key)
        now = timezone.now()

        data = coll.find(
            {'$and':
                [
                    {'key': key},
                    {'$or': [
                        {'expires': {'$gt': now}},
                        {'expires': None},
                    ]}
                ]
            }
        )

        return data.count() > 0

    @reconnect()
    def clear(self):
        coll = self._get_collection()
        if not 'capped' in self._db.command("collstats", self._collection_name):
            coll.remove({})
        else:
            coll.update({}, {'$set':{'expires':timezone.now()}})

    def _get_collection(self):
        if not getattr(self, '_coll', None):
            self._initialize_collection()

        return self._coll

    def _initialize_collection(self):
        if self._username is not None:
            self.connection = pymongo.MongoClient('mongodb://{0}:{1}@{2}:{3}/{4}'.format(self._username, self._password, self._host, self._port, self._database))
        else:
            self.connection = pymongo.MongoClient('mongodb://{0}:{1}/'.format(self._host, self._port))
        self._db = self.connection[self._database]
        if self._collection_name not in self._db.collection_names():
            options = {}
            if self._max_entries is not None:
                # Create a capped collection
                options.update({'capped':True, 'size':self._max_entries})
            
            self._db.create_collection(self._collection_name, **options)
            collection = self._db[self._collection_name]

            if self.default_timeout is not None:
                # Create a TTL index on "expires" field
                collection.create_index(
                    [("expires", pymongo.DESCENDING),],
                    expireAfterSeconds = 0,
                )
            
            # Create an index on "key"/"expires" fields
            collection.create_index([('key', pymongo.ASCENDING),('expires', pymongo.ASCENDING),])

        self._coll = self._db[self._collection_name]
