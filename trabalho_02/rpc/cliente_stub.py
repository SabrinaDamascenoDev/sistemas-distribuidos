import urllib.request
import json
from rpc.mensagem import MensagemRPC

class ClienteProxy:
    def __init__(self, host, port, object_reference):
        self.url = f"http://{host}:{port}/rpc"
        self.req_id_counter = 0
        self.object_reference = object_reference

    def doOperation(self, methodId, arguments):
        self.req_id_counter += 1
        
        payload = MensagemRPC.empacotar_requisicao(
            self.req_id_counter, self.object_reference, methodId, arguments
        )
        
        req = urllib.request.Request(self.url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        try:
            with urllib.request.urlopen(req) as response:
                reply_bytes = response.read()
                reply_dict = json.loads(reply_bytes.decode('utf-8'))
                return reply_dict.get("result")
        except Exception as e:
            return {"erro": str(e)}
