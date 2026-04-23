def allow(request):
    return {"status": "ok", "request": request}


def deny(request):
    return {"status": "deny", "request": request}


def audit(message):
    return message


def first(user, request):
    if user.is_admin:
        return allow(request)
    audit("denied")
    return deny(request)


def second(actor, req):
    if actor.is_admin:
        return allow(req)
    audit("denied")
    return deny(req)
