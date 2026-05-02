import time

def is_double_click(context, key="last_click", delay=1):
    now = time.time()
    last = context.user_data.get(key, 0)

    if now - last < delay:
        return True

    context.user_data[key] = now
    return False