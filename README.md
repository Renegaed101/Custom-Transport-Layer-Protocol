# Custom-Transport-Layer-Protocol
A transport layer protocol developed by me during university. (TCP, UDP are transport layer protocols)

## To run
Server: 
    python3 sor-server.py server_ip_address server_udp_port_number server_buffer_size server_payload_length

where the SoR server binds to server_ip_address and server_udp_port for RDP, with
server_buffer_size for each RDP connection to receive data, and server_payload_length to send data

Client:
    python3 sor-client.py server_ip_address server_udp_port_number client_buffer_size client_payload_length
    read_file_name write_file_name [read_file_name write_file_name]

where the SoR client connects to the SoR server at server_ip_address and server_udp_port, with
client_buffer_size for each RDP connection to receive data, and client_payload_length to send data, and
requests the file with read_file_name from the SoR server on H2 and writes to write_file_name on H1. “diff
read_file_name write_file_name” can help you verify whether the file is transferred correctly. If there are
multiple pairs of read_file_name and write_file_name in the command line, it indicates that the SoR client shall
request these files from the SoR server in a persistent HTTP session over an RDP connection.

## Features
SoR Server:
Supports flow control via window as well as error control via Timeout Feature as well as Duplicate Ack feature.
Supports Multiple Clients
Supports Multiple Files
Supports Pipelined and Non-Pipelined HTTP requests
Supports RST packet for a given client with all other clients unaffected
SoR Client
Supports flow control via window as well as error control via Timeout Feature
Will reset if RST packet received
Included in the source code is both the pipelined http request implementation (default) as well as the unpipelined implementation. Comments indicate which sections should be uncommented/commented to switch between the two implementations
