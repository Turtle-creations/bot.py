<<<<<<< HEAD
import time

def is_double_click(context, key="last_click", delay=1):
    now = time.time()
    last = context.user_data.get(key, 0)

    if now - last < delay:
        return True

    context.user_data[key] = now
=======
import time

def is_double_click(context, key="last_click", delay=1):
    now = time.time()
    last = context.user_data.get(key, 0)

    if now - last < delay:
        return True

    context.user_data[key] = now
>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return False