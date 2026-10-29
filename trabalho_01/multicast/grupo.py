"""
Utilitários de multicast IP (UDP) usados pela questão 4 e pela questão extra.

Equivalências com a API Java (MulticastSocket):
    joinGroup(grupo)   -> entrar_no_grupo()  (opção IP_ADD_MEMBERSHIP)
    leaveGroup(grupo)  -> sair_do_grupo()    (opção IP_DROP_MEMBERSHIP)
    setTimeToLive(ttl) -> IP_MULTICAST_TTL
"""

import ipaddress
import socket
import struct
import sys

IP_MULTICAST_ALL = getattr(socket, "IP_MULTICAST_ALL", 49)


def validar_grupo(grupo):
    """Garante que o endereço é classe D (224.0.0.0 a 239.255.255.255)."""
    if not ipaddress.IPv4Address(grupo).is_multicast:
        raise ValueError(f"{grupo} não é um endereço multicast (classe D)")
    return grupo


def _mreq(grupo, interface):
    return struct.pack("4s4s", socket.inet_aton(grupo), socket.inet_aton(interface))


def criar_socket_receptor(grupo, porta, interface="0.0.0.0"):
    """Cria o socket UDP que escuta a porta do grupo (ainda sem entrar nele)."""
    validar_grupo(grupo)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):  # vários clientes na mesma máquina/porta
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    if sys.platform.startswith("linux"):
        try:
            sock.setsockopt(socket.IPPROTO_IP, IP_MULTICAST_ALL, 0)
        except OSError:
            pass
        sock.bind((grupo, porta))  
    else:
        sock.bind(("", porta))      
    return sock


def entrar_no_grupo(sock, grupo, interface="0.0.0.0"):
    """joinGroup: avisa o kernel (e os roteadores, via IGMP) que queremos o grupo."""
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, _mreq(grupo, interface))


def sair_do_grupo(sock, grupo, interface="0.0.0.0"):
    """leaveGroup: deixa de receber os datagramas enviados ao grupo."""
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, _mreq(grupo, interface))


def criar_socket_emissor(ttl=1, interface=None):
    """Socket UDP comum para ENVIAR ao grupo (quem envia não precisa entrar no grupo)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)  # entrega local também
    if interface and interface != "0.0.0.0":
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
    return sock