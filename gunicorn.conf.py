def post_worker_init(worker):
    from notifications import start_worker
    start_worker()
