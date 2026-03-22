import logging

from applications import create_app, HKRecorderThreadManager

app = create_app()

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

if __name__ == '__main__':
    app.logger.info("加油站工服检测系统启动，监听 0.0.0.0:8080")
    app.run(threaded=True, host='0.0.0.0', port=8080)