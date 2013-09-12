# -*- coding: utf-8 -*-
# Author Karol Sikora <karol.sikora@laboratorium.ee>, (c) 2012

try:
    import cPickle as pickle
except ImportError:
    import pickle
import base64
import re
from datetime import datetime, timedelta
import pymongo
from pymongo.errors import OperationFailure, TimeoutError
from django.core.cache.backends.base import BaseCache


class MongoDBCache(BaseCache):
    def __init__(self, location, params):
        BaseCache.__init__(self, params)
        self.location = location
        options = params.get('OPTIONS', {})
        self._host = options.get('HOST', 'localhost')
        self._port = options.get('PORT', 27017)
        self._database = options.get('DATABASE', 'django_cache')
        self._collection = location

    def make_key(self, key, version=None):
        """
         Additional regexp to remove $ and . cachaters,
        as they cause special behaviour in mongodb
        """
        key = super(MongoDBCache, self).make_key(key, version)

        return re.sub(r'\$|\.', '', key)

    def add(self, key, value, timeout=None, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)

        return self._base_set('add', key, value, timeout)

    def set(self, key, value, timeout=None, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)

        return self._base_set('set', key, value, timeout)

    def _base_set(self, mode, key, value, timeout=None):
        if not timeout:
            timeout = self.default_timeout

        now = datetime.utcnow()
        expires = now + timedelta(seconds=timeout)
        coll = self._get_collection()
        pickled = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
        encoded = base64.encodestring(pickled).strip()

        count = coll.count()
        if count > self._max_entries:
            self._cull()
        data = coll.find_one({'key': key})

        try:
            if data and (mode == 'set'
                         or (mode == 'add' and data['expires'] > now)):
                coll.update(
                    {'_id': data['_id']},
                    {'$set': {'data': encoded, 'expires': expires}},
                    safe=True
                )
            else:
                coll.insert(
                    {'key': key, 'data': encoded, 'expires': expires},
                    safe=True
                )
        #TODO: check threadsafety
        except (OperationFailure, TimeoutError):
            return False
        else:
            return True

    def get(self, key, default=None, version=None):
        coll = self._get_collection()
        key = self.make_key(key, version)
        self.validate_key(key)
        now = datetime.utcnow()

        data = coll.find_one({'key': key})
        if not data:
            return default
        if data['expires'] < now:
            coll.remove(data['_id'])
            return default

        unencoded = base64.decodestring(data['data'])
        unpickled = pickle.loads(unencoded)

        return unpickled

    def get_many(self, keys, version=None):
        coll = self._get_collection()
        now = datetime.utcnow()
        out = {}
        parsed_keys = {}
        to_remove = []

        for key in keys:
            pkey = self.make_key(key, version)
            self.validate_key(pkey)
            parsed_keys[pkey] = key

        data = coll.find({'key': {'$in': parsed_keys.keys()}})
        for result in data:
            if result['expires'] < now:
                to_remove.append(result['_id'])
            unencoded = base64.decodestring(result['data'])
            unpickled = pickle.loads(unencoded)
            out[parsed_keys[result['key']]] = unpickled

        if to_remove:
            coll.remove({'_id': {'$in': to_remove}})

        return out

    def delete(self, key, version=None):
        key = self.make_key(key, version)
        self.validate_key(key)
        coll = self._get_collection()
        coll.remove({'key': key})

    def has_key(self, key, version=None):
        coll = self._get_collection()
        key = self.make_key(key, version)
        self.validate_key(key)
        data = coll.find_one({'key': key, 'expires': {'$gt': datetime.utcnow()}})

        return data is not None

    def clear(self):
        coll = self._get_collection()
        coll.remove(None)

    def _cull(self):
        if self._cull_frequency == 0:
            self.clear()
            return
        coll = self._get_collection()
        coll.remove({'expires': {'$lte': datetime.utcnow()}})
        #TODO: implement more agressive cull

    def _get_collection(self):
        if not getattr(self, '_coll', None):
            self._initialize_collection()

        return self._coll

    def _initialize_collection(self):
        #monkey.patch_socket()
        self.connection = pymongo.MongoClient(self._host, self._port)
        self._db = self.connection[self._database]
        self._coll = self._db[self._collection]
