import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.loja_service import LojaService
from rpc.servidor_skeleton import ServidorRPC

if __name__ == "__main__":
    servico_loja = LojaService()
    servidor = ServidorRPC("127.0.0.1", 8000)
    servidor.registrar_objeto("ServicoLoja", servico_loja)
    servidor.iniciar()
