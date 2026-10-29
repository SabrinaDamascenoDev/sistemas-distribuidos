import json

class MensagemRPC:
    @staticmethod
    def empacotar_requisicao(req_id, obj_ref, method_id, args):
        return json.dumps({
            "messageType": 0,
            "requestID": req_id,
            "objectReference": obj_ref,
            "methodID": method_id,
            "arguments": args
        }).encode('utf-8')

    @staticmethod
    def empacotar_resposta(req_id, result):
        return json.dumps({
            "messageType": 1,
            "requestID": req_id,
            "result": result
        }).encode('utf-8')
