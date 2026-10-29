import java.io.*;
import java.net.*;
import java.util.*;

/*
 * Cliente de Ping sobre UDP. Envia 10 pings pro servidor, um a cada ~1 segundo, e espera no maximo 1 segundo pela resposta de cada um. Se estourar o tempo, considera perdido.
 */
public class PingClient {

    public static void main(String[] args) throws Exception {

        if (args.length != 2) {
            System.out.println("Uso: java PingClient host port");
            return;
        }

        InetAddress host = InetAddress.getByName(args[0]);
        int port = Integer.parseInt(args[1]);
        DatagramSocket socket = new DatagramSocket();

        socket.setSoTimeout(1000);

        long minRTT = Long.MAX_VALUE;
        long maxRTT = 0;
        long somaRTT = 0;
        int recebidos = 0;

        for (int seq = 0; seq < 10; seq++) {

            // marca o tempo de envio 
            long inicio = System.currentTimeMillis();

            // monta a mensagem no formato PING
            String mensagem = "PING " + seq + " " + inicio + "\r\n";
            byte[] dados = mensagem.getBytes();
            DatagramPacket envio = new DatagramPacket(dados, dados.length, host, port);
            socket.send(envio);

            // pacote pra receber a resposta
            byte[] buffer = new byte[1024];
            DatagramPacket resposta = new DatagramPacket(buffer, buffer.length);

            try {
                socket.receive(resposta);

                long rtt = System.currentTimeMillis() - inicio;
                System.out.println("PING " + seq + "   RTT = " + rtt + " ms");

                // vai guardando pra estatistica no final
                if (rtt < minRTT) minRTT = rtt;
                if (rtt > maxRTT) maxRTT = rtt;
                somaRTT += rtt;
                recebidos++;

            } catch (SocketTimeoutException e) {
                System.out.println("PING " + seq + "   sem resposta (perdido)");
            }
            Thread.sleep(1000);
        }

        socket.close();
        int perdidos = 10 - recebidos;
        System.out.println();
        System.out.println("--- estatisticas do ping ---");
        System.out.println("10 enviados, " + recebidos + " recebidos, "
                + perdidos + " perdidos");

        if (recebidos > 0) {
            System.out.println("rtt min = " + minRTT + " ms");
            System.out.println("rtt max = " + maxRTT + " ms");
            System.out.println("rtt medio = " + (somaRTT / recebidos) + " ms");
        }
    }
}
