from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from rpc.mensagem import MensagemRPC

class RPCHandler(BaseHTTPRequestHandler):
    objetos_remotos = {}
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        req = json.loads(post_data.decode('utf-8'))
        
        if req['messageType'] == 0:
            obj_ref = req['objectReference']
            method_id = req['methodID']
            args = req['arguments']
            
            resultado = None
            
            if obj_ref in self.objetos_remotos:
                obj = self.objetos_remotos[obj_ref]
                if hasattr(obj, method_id):
                    metodo = getattr(obj, method_id)
                    resultado = metodo(args)
                else:
                    resultado = {"erro": "Método não encontrado"}
            else:
                resultado = {"erro": "Objeto remoto não encontrado"}
                
            self.sendReply(req['requestID'], resultado)

    def sendReply(self, req_id, result):
        reply_bytes = MensagemRPC.empacotar_resposta(req_id, result)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(reply_bytes)

class ServidorRPC:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.objetos = {}
        
    def registrar_objeto(self, nome, obj):
        self.objetos[nome] = obj
        
    def iniciar(self):
        RPCHandler.objetos_remotos = self.objetos
        server_address = (self.host, self.port)
        httpd = HTTPServer(server_address, RPCHandler)
        print(f"Servidor RMI/RPC rodando em http://{self.host}:{self.port} ...")
        httpd.serve_forever()
