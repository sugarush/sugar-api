import ujson

from sanic import Blueprint

from . acl import acl
from . error import Error
from . header import content_type, accept, jsonapi
from . preflight import preflight
from . webtoken import WebToken, webtoken


class JSONAPIMixin(object):

    __acl__ = None

    def to_jsonapi(self):
        data = { }

        data['type'] = self._table
        data['id'] = self.id
        data['attributes'] = self.serialize()

        return data

    @classmethod
    def from_jsonapi(cls, data):
        id = data.get('id')
        attributes = data.get('attributes')

        model = cls(attributes)

        if id:
            model.id = id

        return model

    @classmethod
    def resource(cls, *args, **kargs):

        if not len(args) > 0:
            args = [ cls._table ]

        bp = Blueprint(*args, **kargs)

        url = '/{path}'.format(path=cls._table)

        @bp.options(url)
        async def options(*args, **kargs):
            return preflight(methods=[ 'GET', 'POST' ])

        @bp.options(url + '/<id>')
        async def options(*args, **kargs):
            return preflight(methods=[ 'GET', 'PATCH', 'DELETE' ])

        @bp.get(url)
        @accept
        @webtoken
        @acl('read_all', cls.__acl__, cls)
        async def read(*args, **kargs):
            return await cls._read(*args, **kargs)

        @bp.post(url)
        @content_type
        @accept
        @cls._check_create
        @webtoken
        @acl('create', cls.__acl__, cls)
        async def create(*args, **kargs):
            return await cls._create(*args, **kargs)

        @bp.get(url + '/<id>')
        @accept
        @webtoken
        @acl('read', cls.__acl__, cls)
        async def read(*args, **kargs):
            return await cls._read(*args, **kargs)

        @bp.patch(url + '/<id>')
        @content_type
        @accept
        @cls._check_update
        @webtoken
        @acl('update', cls.__acl__, cls)
        async def update(*args, **kargs):
            return await cls._update(*args, **kargs)

        @bp.delete(url + '/<id>')
        @accept
        @webtoken
        @acl('delete', cls.__acl__, cls)
        async def delete(*args, **kargs):
            return await cls._delete(*args, **kargs)

        return bp

    @classmethod
    def _check_create(cls, handler):
        async def decorator(request, *args, **kargs):

            data = None

            if request.json:
                data = request.json.get('data')

            if not data:
                error = Error(
                    title = 'Create Error',
                    detail = 'No data supplied.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            if not isinstance(data, dict):
                error = Error(
                    title = 'Create Error',
                    detail = 'Data is not a JSON object.',
                    links = {
                        'about': 'https://jsonapi.org/format/#crud-creating'
                    },
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            type = data.get('type')

            if not type:
                error = Error(
                    title = 'Create Error',
                    detail = 'Type is missing.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            if not type == cls._table:
                error = Error(
                    title = 'Create Error',
                    detail = 'Provided type does not match resource type.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            attributes = data.get('attributes')

            if not attributes:
                error = Error(
                    title = 'Create Error',
                    detail = 'No attributes supplied.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            return await handler(request, *args, **kargs)

        return decorator

    @classmethod
    def _check_update(cls, handler):
        async def decorator(request, *args, **kargs):

            data = None

            if request.json:
                data = request.json.get('data')

            if not data:
                error = Error(
                    title = 'Update Error',
                    detail = 'No data provided.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            if not isinstance(data, dict):
                error = Error(
                    title = 'Update Error',
                    detail = 'Invalid data attribute.',
                    links = {
                        'about': 'https://jsonapi.org/format/#crud-creating'
                    },
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            type = data.get('type')

            if not type:
                error = Error(
                    title = 'Update Error',
                    detail = 'Type is missing.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            if not type == cls._table:
                error = Error(
                    title = 'Update Error',
                    detail = 'Type in payload does not match collection type.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            id = kargs.get('id')
            _id = data.get('id')

            if not _id:
                error = Error(
                    title = 'Update Error',
                    detail = 'ID is missing.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            if not id == _id:
                error = Error(
                    title = 'Update Error',
                    detail = 'ID provided does not match ID in the URL.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            attributes = data.get('attributes')

            if not attributes:
                error = Error(
                    title = 'Update Error',
                    detail = 'No attributes provided.',
                    status = 403
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

            return await handler(request, *args, **kargs)

        return decorator

    @classmethod
    async def _create(cls, request, token=None):

        # XXX: The request has already been verified
        # XXX: in the decorator cls._check_create.

        data = request.json.get('data')

        try:
            model = cls.from_jsonapi(data)

        except Exception as e:
            error = Error(
                title = 'Create Error',
                detail = str(e),
                status = 403
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

        try:
            if model.id and await cls.exists(model.id):
                message = '{model} {id} already exists.'.format(
                    model = cls.__name__,
                    id = model.id
                )
                error = Error(
                    title = 'Create Error',
                    detail = message,
                    status = 409
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=409)

        except Exception as e:
            error = Error(
                title = 'Create Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        try:
            await model.save()

        except Exception as e:
            error = Error(
                title = 'Create Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        return jsonapi({ 'data': model.to_jsonapi() }, status=201)

    @classmethod
    async def _read(cls, request, id=None, token=None):
        if id:

            try:
                model = await cls.find_by_id(id)

            except Exception as e:
                error = Error(
                    title = 'Read Error',
                    detail = str(e),
                    status = 500
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

            if not model:
                error = Error(
                    title = 'Read Error',
                    detail = 'No data found.',
                    status = 404
                )
                return jsonapi({
                    'data': None,
                    'errors': [ error.serialize() ]
                }, status=404)

            return jsonapi({ 'data': model.to_jsonapi() }, status=200)

        else:

            try:
                models = [ ]

                query_json = request.args.get('query', '{ }')

                try:
                    query = ujson.loads(query_json)

                except Exception as e:
                    error = Error(
                        title = 'Read Error',
                        detail = str(e),
                        status = 403
                    )
                    return jsonapi({
                        'errors': [ error.serialize() ]
                    }, status=403)

                sort = request.args.get('sort')

                if sort:

                    try:
                        sort = filter(lambda item: item != '', sort.split(','))

                    except Exception as e:
                        error = Error(
                            title = 'Read Error',
                            detail = str(e),
                            status = 403
                        )
                        return jsonapi({
                            'errors': [ error.serialize() ]
                        }, status=403)

                    def prepare(item):
                        result = [ ]

                        if item.startswith('-'):
                            result.append(-1)
                        else:
                            result.append(1)

                        item = item.strip('-')
                        result.insert(0, item)

                        return result

                    sort = list(map(prepare, sort))

                offset = int(request.args.get('page[offset]', 0))
                limit = int(request.args.get('page[limit]', 100))

                async for model in cls.find(query, sort=sort, skip=offset, limit=limit):
                    models.append(model)

            except Exception as e:
                error = Error(
                    title = 'Read Error',
                    detail = str(e),
                    status = 500
                )
                return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

            if not models:
                error = Error(
                    title = 'Read Error',
                    detail = 'No data found.',
                    status = 404
                )
                return jsonapi({
                    'data': [ ],
                    'errors': [ error.serialize() ]
                }, status=404)

            return jsonapi({
                'data': list(map(lambda model: model.to_jsonapi(), models)),
                'meta': {
                    'offset': offset,
                    'limit': limit,
                    'total': await cls.count()
                }
            }, status=200)

    @classmethod
    async def _update(cls, request, id=None, token=None):

        # XXX: The request has already been verified
        # XXX: in the decorator cls._check_update.

        data = request.json.get('data')

        attributes = data.get('attributes')

        try:
            model = await cls.find_by_id(id)

        except Exception as e:
            error = Error(
                title = 'Update Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        try:
            model.update(attributes)

        except Exception as e:
            error = Error(
                title = 'Update Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        if not model.id == id:
            error = Error(
                title = 'Update Error',
                detail = 'The Model\'s ID does not match the ID in the URL.',
                status = 403
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=403)

        try:
            await model.save()

        except Exception as e:
            error = Error(
                title = 'Update Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        return jsonapi({ 'data': model.to_jsonapi() }, status=200)

    @classmethod
    async def _delete(cls, request, id, token=None):

        try:
            model = await cls.find_by_id(id)

        except Exception as e:
            error = Error(
                title = 'Delete Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        try:
            await model.delete()

        except Exception as e:
            error = Error(
                title = 'Delete Error',
                detail = str(e),
                status = 500
            )
            return jsonapi({ 'errors': [ error.serialize() ] }, status=500)

        return jsonapi({ }, status=200)