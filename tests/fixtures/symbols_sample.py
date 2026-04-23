class Greeter:
    def format_name(self, value):
        if value:
            return value.strip()
        return "guest"


def outer(flag):
    def inner():
        return 1

    if flag:
        return inner()
    return 0
