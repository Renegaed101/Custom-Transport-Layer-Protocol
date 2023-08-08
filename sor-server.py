import sys
import socket
import time
import re
import select
import threading

inputs = []
outputs = []
connections = {}
connectionLock = threading.Lock()

def main():

    s = socket.socket (socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(0)
    s.bind((sys.argv[1],int(sys.argv[2])))

    inputs.append(s)
    outputs.append(s)

    rpattern = re.compile ("(.+)\n(Sequence: (\d+)\n)?(Length: (\d+)\n)?(Acknowledgment: (-?\d+)\n)?(Window: (\d+)\n)?\n([\s\S]*)")
    httpPattern = re.compile("GET /(.*) HTTP/1.0(\n(.+):\s*(\S+)\s*)?\n\n")
    while True:
        readable, writable, exceptional = select.select(inputs,outputs,inputs)

        for i in readable:
            data,addr = i.recvfrom(int(sys.argv[3]) + 1000)
            if addr not in connections:
                connectionLock.acquire()
                connections[addr] = [data.decode()]
                connectionLock.release()
                x = threading.Thread (target = connectionThread, args = (addr,rpattern,httpPattern,), daemon=True)
                x.start()   
            else:
                connectionLock.acquire()
                connections[addr].append(data.decode())
                connectionLock.release()  


def connectionThread(addr,rpattern,httpPattern):
    """A thread function dedicated to each connection"""
    connectionStats = [0,0,False,{},0,0,[],[-2,0]] # [ClientWindow, ClientAck, ConnectionKeptAlive,Packets,SeqCounter,clientState,outgoingMessages,DupAck]
    timeoutStats = [0,0,0]
    
    while True:
        connectionLock.acquire()
        try:
            message = connections[addr][0]
            del connections[addr][0]
        except IndexError:
            message = None
        connectionLock.release()

        if message != None:
            handleMessage(message,rpattern,connectionStats,httpPattern,timeoutStats,addr)

        timeoutCheck(timeoutStats,connectionStats)

        readable, writable, exceptional = select.select([],outputs,[])
        
        for i in writable:
            try:
                j = connectionStats[6][0]
                while connectionStats[0] - connectionStats[3][j][1] >= 0:
                    connectionStats[3][j][0] = re.sub("Acknowledgment: \d+\n","Acknowledgment: %d\n" % (connectionStats[1]),connectionStats[3][j][0])
                    i.sendto(connectionStats[3][j][0].encode(),addr)
                    del connectionStats[6][0]
                    connectionStats[0] -= connectionStats[3][j][1]
                    j = connectionStats[6][0]
            except IndexError:
                if connectionStats[5] == 2:
                    finACK = "ACK\nSequence: " + str(connectionStats[4]) + "\nLength: 0" +\
                        "\nAcknowledgment: " + str(connectionStats[1]) + "\nWindow: " + sys.argv[3] + "\n\n"
                    i.sendto(finACK.encode(),addr)
                    return
                if connectionStats[5] == 3:
                    outputs[0].sendto("RST\n\n".encode(),addr)
                    return


def handleMessage(message,rpattern,connectionStats,httpPattern,timeoutStats,addr) :
    """Processes received RDP packets"""
    m = rpattern.match(message)
    if m != None:
        if 'DAT' in m.group(1):
                if int(m.group(5)) > int(sys.argv[3]):
                    connectionStats[5] = 3
                    connectionStats[6] = []
                    timeoutStats[1] = time.time() + 30
                    return
        if int(m.group(3)) == connectionStats[1]:
            if "FIN" in m.group(1):
                connectionStats[1] += 1
                connectionStats[4] += 1
                connectionStats[5] = 2
            if 'ACK' in m.group(1):
                connectionStats[0] = int(m.group(9))
                timeoutUpdate(connectionStats,timeoutStats,int(m.group(7)))
                dupAckUpdate(connectionStats,int(m.group(7)))
            if 'SYN' in m.group(1):
                connectionStats[1] = 1
            if 'DAT' in m.group(1):
                connectionStats[1] += int(m.group(5))
                handleHTTP(m.group(10),httpPattern,connectionStats,addr)
        else:
           if "ACK" in m.group(1):
               connectionStats[0] = int(m.group(9))
               timeoutUpdate(connectionStats,timeoutStats,int(m.group(7)))
               dupAckUpdate(connectionStats,int(m.group(7)))
        

def handleHTTP(httpMessage,httpPattern,connectionStats,addr):
    """Processes recieved HTTP Packets"""

    #Check if pipelined request and handle
    splitReq = []
    logInfo = []
    payloadLength = int(sys.argv[4])
    multipleReq = False
    badRequest = "HTTP/1.0 400 Bad Request\r\n\r\n"
    if httpMessage.count("\n\n") > 1:
        splitReq = httpMessage.split("\n\n")
        del splitReq[-1]
        multipleReq = True
    #Loop to process both single requests and pipilined requests
    #Logs are generated here as well bot not yet printed
    while len(splitReq) != 0 or multipleReq == False:
        if multipleReq == False:
            message = httpMessage
        else:
            message = splitReq[0] + "\n\n"
        m = httpPattern.match(message)
        if m:
            try:    
                file = open (m.group(1), "r")
            except FileNotFoundError:
                file = None
            #Case file is found
            if file != None:
                if m.group(2) == None:
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 200 OK"))
                    if connectionStats[2] == True:
                        httpHeader = "HTTP/1.0 200 OK\r\nConnection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)                        
                    else:
                        httpHeader = "HTTP/1.0 200 OK\r\n\r\n" 
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    connectionStats[2] = False
                    break
                elif m.group(3).lower() == "connection" and m.group(4).lower() == "close":
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 200 OK"))
                    if connectionStats[2] == True:
                        httpHeader = "HTTP/1.0 200 OK\r\nConnection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader) 
                    else:
                        httpHeader = "HTTP/1.0 200 OK\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader) 
                    connectionStats[2] = False 
                    break
                elif m.group(3).lower() == "connection" and m.group(4).lower() == "keep-alive":
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 200 OK"))
                    httpHeader = "HTTP/1.0 200 OK\r\nConnection: Keep-alive\r\n\r\n"
                    packetize (payloadLength,file,connectionStats,httpHeader)  
                    connectionStats[2] = True
                else:
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 400 Bad Request"))
                    if connectionStats[2] == True:
                        httpHeader = badRequest[:-2] + "Connection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    else:
                        httpHeader = badRequest
                        packetize (payloadLength,file,connectionStats,httpHeader) 
                    connectionStats[2] = False
                    break
            #Case file is not found
            else:
                if m.group(2) == None:
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 404 Not Found"))
                    if connectionStats[2] == True:
                        httpHeader = "HTTP/1.0 404 Not Found\r\nConnection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    else:
                        httpHeader = "HTTP/1.0 404 Not Found\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    connectionStats[2] = False
                    break
                elif m.group(3).lower() == "connection" and m.group(4).lower() == "close":
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 404 Not Found"))
                    if connectionStats[2] == True:
                        httpHeader = "HTTP/1.0 404 Not Found\r\nConnection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    else:
                        httpHeader = "HTTP/1.0 404 Not Found\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader) 
                    connectionStats[2] = False
                    break
                elif m.group(3).lower() == "connection" and m.group(4).lower() == "keep-alive":
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 404 Not Found"))
                    httpHeader = "HTTP/1.0 404 Not Found\r\nConnection: Keep-alive\r\n\r\n"
                    packetize (payloadLength,file,connectionStats,httpHeader)
                    connectionStats[2] = True  
                else:
                    logInfo.append((message[:message.index("\n")],"HTTP/1.0 400 Bad Request"))
                    if connectionStats[2] == True:
                        httpHeader = badRequest[:-2] + "Connection: Close\r\n\r\n"
                        packetize (payloadLength,file,connectionStats,httpHeader)
                    else:
                        connectionStats[2] = False
                    break
        #Case request format is not Valid        
        else:
            logInfo.append((message[:message.index("\n")],"HTTP/1.0 400 Bad Request"))
            if connectionStats[2] == True:
                httpHeader = badRequest[:-2] + "Connection: Close\r\n\r\n"
                packetize (payloadLength,None,connectionStats,httpHeader)
            else:
                httpHeader = badRequest
                packetize (payloadLength,None,connectionStats,httpHeader)
            connectionStats[2] = False  
            break  
        #Loop Maintenance           
        if multipleReq == True:
            del splitReq[0]
        multipleReq = True
    if connectionStats[2] == False:
        connectionStats[3][connectionStats[6][-1]][0] = "FIN|" + connectionStats[3][connectionStats[6][-1]][0]
        connectionStats[3][connectionStats[6][-1]][2] += 1
    while len(logInfo) != 0:
                print ((time.strftime("%a %b %d %H:%M:%S %Z %Y: ",time.localtime())) + addr[0] + ":" +\
                        str(addr[1]) + " " + logInfo[0][0] + "; " + logInfo[0][1])
                del (logInfo[0])

                
def packetize (payloadLength,file,connectionStats,httpHeader):
        """Constructs packets for given file"""
        package = ""        
        if connectionStats[5] == 0:
            firstHeader = "SYN|DAT|ACK"
        else:
            firstHeader = "DAT|ACK" 
        if file != None:
            for line in file:
                package += line          
        chunk = package[0:payloadLength-len(httpHeader)]
        connectionStats[3][connectionStats[4]] = [firstHeader + "\nSequence: " + str(connectionStats[4]) + "\nLength: " + str(len(chunk) + len(httpHeader)) +\
            "\nAcknowledgment: " + str(connectionStats[1]) + "\nWindow: " + sys.argv[3] + "\n\n" + httpHeader + chunk, len(chunk) + len(httpHeader), connectionStats[4]+len(chunk)+len(httpHeader)]
        connectionStats[6].append(connectionStats[4])
        if connectionStats[5] == 0:
            connectionStats[3][connectionStats[4]][2] += 1
            connectionStats[4] += (1+len(chunk)+len(httpHeader)) # Change to 1 + payloadLength after verifying this works for better performance
            connectionStats[5] = 1
        else:
            connectionStats[4] += (len(chunk) + len(httpHeader)) # Same change here as above
        for i in range (payloadLength-len(httpHeader),len(package),payloadLength):
            chunk = package[i:i+payloadLength]
            connectionStats[3][connectionStats[4]] = ["DAT|ACK\nSequence: " + str(connectionStats[4]) + "\nLength: " + str(len(chunk)) +\
                "\nAcknowledgment: 0" + "\nWindow: " + sys.argv[3] + "\n\n" + chunk, len(chunk), connectionStats[4]+len(chunk)]
            connectionStats[6].append(connectionStats[4])
            connectionStats[4] += len(chunk)

def dupAckUpdate(connectionStats,ack):
    """If three consecutive acks received, insert that packet at front of queue"""
    if ack == -1:
        return
    if connectionStats[7][0] != ack:
        connectionStats[7][0] = ack
        connectionStats[7][1] = 1
    else:
        connectionStats[7][1] += 1
        if connectionStats[7][1] == 3:
            if ack not in connectionStats[6]:
                connectionStats[6].insert(0,ack)
            connectionStats[7][1] = 0 


def timeoutCheck(timeoutStats,connectionStats):
    """ Timeout feature for packets sent out, if acks not received in 0.12 seconds, retransmits those packets"""
    if len(connectionStats[3]) == 0:
        return
    if timeoutStats[1] == 0:
        timeoutStats[0] = 0
        timeoutStats[1] = time.time() + 0.12
        timeoutStats[2] = connectionStats[3][0][2]
    else:
        if time.time() > timeoutStats[1]:
            if timeoutStats[0] not in connectionStats[6]:
                connectionStats[6].insert(0,timeoutStats[0])
                timeoutStats[1] = time.time() + 0.12      

        
def timeoutUpdate(connectionStats,timeoutStats,ack):
    """Updates the timout if ack received for most recently sent out unacked packet"""
    if ack >= timeoutStats[2]:
        try:
            timeoutStats[2] = connectionStats[3][ack][2]
            timeoutStats[0] = ack
            timeoutStats[1] = time.time() + 0.12
        except KeyError:
            pass


if __name__ == '__main__':
    main()