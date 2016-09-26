'''
Web interface to query list/download status
Manage sessions and metrics
'''

import ssl
import os

import yaml
from flask import Flask
from flask import jsonify
from flask import request
from prometheus_client import Counter
from prometheus_client import Gauge
from prometheus_client.exposition import generate_latest
import consul

from biomaj_download.message import message_pb2
from biomaj_download.downloadservice import DownloadService

app = Flask(__name__)

process_metric = Counter("biomaj_process_total", "Bank total process execution.", ['bank'])
process_error_metric = Counter("biomaj_process_errors", "Bank total process errors.", ['bank'])
process_time_metric = Gauge("biomaj_process_time", "Bank process execution time in seconds.", ['bank'])

config_file = 'config.yml'
if 'BIOMAJ_CONFIG' in os.environ:
        config_file = os.environ['BIOMAJ_CONFIG']

config = None
with open(config_file, 'r') as ymlfile:
    config = yaml.load(ymlfile)


def start_server(config):
    context = None
    if config['tls']['cert']:
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_cert_chain(config['tls']['cert'], config['tls']['key'])

    if config['consul']['host']:
        consul_agent = consul.Consult(host=config['consul']['host'])
        consul_agent.agent.service.register('biomaj_process', service_id=config['consul']['id'], port=config['web']['port'], tags=['biomaj'])
        check = consul.Check.http(url=config['web']['local_endpoint'], interval=20)
        consul_agent.agent.check.register(config['consul']['id'] + '_check', check=check, service_id=config['consul']['id'])

    app.run(host='0.0.0.0', port=config['web']['port'], ssl_context=context, threaded=True, debug=config['web']['debug'])


@app.route('/api/process/metrics', methods=['GET'])
def metrics():
    return generate_latest()


@app.route('/api/process/metrics', methods=['POST'])
def add_metrics():
    '''
    Expects a JSON request with an array of {'bank': 'bank_name', 'error': 'error_message', 'executiob_time': seconds_to_execute}
    '''
    procs = request.get_json()
    for proc in procs:
        if 'error' in proc and proc['error']:
            process_error_metric.labels(proc['bank']).inc()
        else:
            process_metric.labels(proc['bank']).inc()
            process_time_metric.labels(proc['bank']).set(proc['execution_time'])
    return jsonify({'msg': 'OK'})


@app.route('/api/process/session/<bank>', methods=['POST'])
def create_session(bank):
    dserv = ProcessService(config_file, rabbitmq=False)
    session = dserv._create_session(bank)
    return jsonify({'session': session})


@app.route('/api/process/session/<bank>/<session>', methods=['DELETE'])
def clean_session(bank, session):
    dserv = ProcessService(config_file, rabbitmq=False)
    biomaj_file_info = message_pb2.Process()
    biomaj_file_info.bank = bank
    biomaj_file_info.session = session
    dserv.clean(biomaj_file_info)
    return jsonify({'msg': 'session cleared'})

@app.route('/api/process/session/<bank>/<session>', methods=['GET'])
def get_session(bank, session):
    error = self.redis_client.get(self.config['redis']['prefix'] + ':' + bank + ':session:' + session + ':error')
    exitcode = self.redis_client.get(self.config['redis']['prefix'] + ':' + bank + ':session:' + session + ':exitcode')
    info = self.redis_client.get(self.config['redis']['prefix'] + ':' + bank + ':session:' + session + ':error:info')
    if exitcode:
        exitcode = int(exitcode)
    else:
        exitcode = -1
    return jsonify({'error': error, 'exitcode': exitcode, 'info': info})

if __name__ == "__main__":
    start_server(config)