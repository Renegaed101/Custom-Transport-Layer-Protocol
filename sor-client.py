import sys
import socket
import time
import re
import select

inputs = []
outputs = []
curAck = -1
seqNo = 0
currentWriteFile = ["",-1]
clientState = 0
bufferlist = []
connectionClose = 0
windowTimeout = 0

def main():
    global curAck
    global seqNo
    global windowTimeout
    readFiles = []
    writeFiles = {}
    packets = {}
    outgoingMessages = []

    rpattern = re.compile ("(.+)\n(Sequence: (\d+)\n)?(Length: (\d+)\n)?(Acknowledgment: (-?\d+)\n)?(Window: (\d+)\n)?\n([\s\S]*)")
    httpPattern = re.compile("(HTTP/1.0 (.+)(\r\n(.+):\s*(\S+)\s*)?\r\n\r\n)?([\s\S]*)")

    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.setblocking(0)
    serverTuple = (sys.argv[1],int(sys.argv[2]))
    inputs.append(c)
    outputs.append(c)
    clientWindow = sys.argv[3]
    clientTimeout = [0,0,0]

    for i in range(5,len(sys.argv)):
        if i % 2 != 0:
            readFiles.append(sys.argv[i])
        else:
            writeFiles[sys.argv[i]] = []
    
    """"
    x = 0
    while x < len(readFiles):
        if x == 0:
            requestHead = "SYN|DAT|ACK"
        else:
            requestHead = "DAT|ACK"
        httpRequest = 'GET /%s HTTP/1.0\nConnection: keep-alive\n\n' % (readFiles[x])
        requestPacket = requestHead + '\nSequence: %d\nLength: %d\nAcknowledgment: %d\nWindow: %s\n\n%s' % (seqNo,len(httpRequest),curAck,clientWindow,httpRequest)
        if x == len(readFiles) - 1:
            requestPacket = requestPacket[:-24] + "\n"
        packets[seqNo] = [requestPacket,seqNo]
        outgoingMessages.append(seqNo)
        if x == 0:
            packets[seqNo][1] += len(httpRequest) + 1
            seqNo += len(httpRequest)+1
        else:
            packets[seqNo][1] += len(httpRequest)
            seqNo += len(httpRequest)
        x += 1
    """

    # THIS IS THE PIPELINED IMPLEMENTAION BETWEEN THE ARROWS, COMMENT THIS SECTION OUT AND UNCOMMENT ABOVE SECTION 
    # TO USE NON PIPELINED IMPLEMENTATION
    #------------------------------------->
    httpRequest = ""
    for i in readFiles:
        httpRequest += 'GET /%s HTTP/1.0\nConnection: keep-alive\n\n' % (i)
    httpRequest = httpRequest[:-24] + "\n"
    requestPacket = 'SYN|DAT|ACK\nSequence: 0\nLength: %d\nAcknowledgment: %d\nWindow: %s\n\n%s' % (len(httpRequest),curAck,clientWindow,httpRequest)
    packets[seqNo] = [requestPacket,len(httpRequest) + 1]
    seqNo = len(httpRequest) + 1
    #------------------------------------->

    windowTimeout = time.time() + 0.12
    while True:
        readable, writable, exceptional = select.select(inputs,outputs,inputs)

        for i in readable:
            data,addr = i.recvfrom(int(clientWindow)+1000)  
            handleMessage(data.decode(),rpattern,serverTuple,i,httpPattern,writeFiles,clientTimeout,packets)
            windowTimeout = time.time() + 0.12        
        for i in writable:
            timeoutCheck(clientTimeout, packets, outgoingMessages)
            windowProbe(i,serverTuple,rpattern)
            if len(outgoingMessages) > 0:
                packets[outgoingMessages[0]][0] = re.sub("Acknowledgment: -?\d+\n","Acknowledgment: %d\n" % (curAck),packets[outgoingMessages[0]][0])
                m = rpattern.match(packets[outgoingMessages[0]][0])
                createLog(m,"Send")
                i.sendto(packets[outgoingMessages[0]][0].encode(),serverTuple)
                del outgoingMessages[0]


def timeoutUpdate(clientTimeout,packets,ack):
    """Updates the timout if ack received for most recently sent out unacked packet"""
    if ack >= clientTimeout[2]:
        try:
            clientTimeout[2] = packets[ack][1]
            clientTimeout[0] = ack
            clientTimeout[1] = time.time() + 0.12
        except KeyError:
            clientTimeout[1] = None
            pass


def timeoutCheck(clientTimeout,packets,outgoingMessages):
    """ Timeout feature for packets sent out, if acks not received in 0.12 seconds, retransmits those packets"""
    if clientTimeout[1] == None:
        return
    if clientTimeout[1] == 0:
        clientTimeout[0] = 0
        clientTimeout[1] = time.time() + 0.12
        clientTimeout[2] = packets[0][1]
    else:
        if time.time() > clientTimeout[1]:
            if clientTimeout[0] not in outgoingMessages:
                outgoingMessages.insert(0,clientTimeout[0])
                clientTimeout[1] = time.time() + 0.12


def windowProbe(i,serverTuple,rpattern):
    """ If not packets received for 0.12 seconds, send out a window update to server"""
    global windowTimeout
    global seqNo
    global curAck

    if time.time() > windowTimeout:
        responsePacket = "ACK\nSequence: " + str(seqNo) + "\nLength: 0" +\
        "\nAcknowledgment: " + str(curAck) + "\nWindow: " + sys.argv[3] + "\n\n"
        m = rpattern.match(responsePacket)
        createLog(m,"Send")
        i.sendto(responsePacket.encode(),serverTuple)
        windowTimeout = time.time() + 0.12
            

def handleMessage(message,rpattern,serverTuple,i,httpPattern,writeFiles,clientTimeout,packets):
    """Function to process RDP packets"""
    global curAck
    global seqNo
    global connectionClose

    m = rpattern.match(message)
    createLog(m,"Receive")
    if curAck == -1:
        curAck = 0

    if m != None:
            if "RST" in m.group(1):
                exit()
            if curAck <= int(m.group(3)):
                if  'ACK' in m.group(1):
                    timeoutUpdate(clientTimeout,packets,int(m.group(7)))
                if 'DAT' in m.group(1) and "FIN" in m.group(1) and "SYN" in m.group(1):
                    connectionClose = 1
                    curAck += int(m.group(5)) + 2
                    handlePayload(m.group(10),httpPattern,writeFiles)
                    build(writeFiles)    
                elif 'DAT' in m.group(1) and 'SYN' in m.group(1):
                    curAck += int(m.group(5)) + 1
                    handlePayload(m.group(10),httpPattern,writeFiles)
                elif 'DAT' in m.group(1) and "FIN" in m.group(1):
                    if curAck == int(m.group(3)):
                        curAck += int(m.group(5)) + 1
                        connectionClose = 1
                        handlePayload(m.group(10),httpPattern,writeFiles)
                        build(writeFiles)
                    elif curAck < int(m.group(3)):
                        buffer(m)
                elif 'DAT' in m.group(1):
                    if curAck == int(m.group(3)):
                        curAck += int(m.group(5))
                        handlePayload(m.group(10),httpPattern,writeFiles)
                    elif curAck < int(m.group(3)):
                        buffer(m)
                elif 'SYN' in m.group(1):
                    curAck = 1
                elif "FIN" in m.group(1):
                    if curAck == int(m.group(3)):
                        connectionClose = 1
                        curAck += 1
                        build(writeFiles)
                    elif curAck < int(m.group(3)):
                        buffer(m)
                bufferProcess(httpPattern,writeFiles)
                responsePacket = "ACK\nSequence: " + str(seqNo) + "\nLength: 0" +\
                "\nAcknowledgment: " + str(curAck) + "\nWindow: " + sys.argv[3] + "\n\n"
                if connectionClose == 1:
                    responsePacket = "FIN|" + responsePacket
                    m = rpattern.match(responsePacket)
                    createLog(m,"Send")
                    i.sendto(responsePacket.encode(),serverTuple)
                    exit()
                else:
                    m = rpattern.match(responsePacket)
                    createLog(m,"Send")       
                    i.sendto(responsePacket.encode(),serverTuple)

           
def build(writeFiles):
    """Once packets for all files have been received, this function writes to final output files"""
    for i,j in writeFiles.items():
        file = open(i,'w')
        for k in j:
            file.write(k)
    

def handlePayload(httpMessage,httpPattern,writeFiles):
    """Builds up packets for each file in order"""
    global currentWriteFile
    m = httpPattern.match(httpMessage)

    if m.group(1) != None:
        currentWriteFile[1] += 1
        l = list(writeFiles)
        currentWriteFile[0] = l[currentWriteFile[1]]
    if m.group(6) != None:
        writeFiles[currentWriteFile[0]].append(m.group(6))


def bufferProcess(httpPattern,writeFiles):
    """Checks if the next required packet is already buffered and proccesses if it is"""
    global curAck
    global bufferlist
    global connectionClose

    try:
        while curAck == bufferlist[0][0]:
            if "FIN" in bufferlist[0][3]:
                connectionClose = 1
                curAck += bufferlist[0][1] + 1
                handlePayload(bufferlist[0][2],httpPattern,writeFiles)
                build(writeFiles)
            else:
                curAck += bufferlist[0][1]
                handlePayload(bufferlist[0][2],httpPattern,writeFiles)
            del bufferlist[0]
    except IndexError:
        pass
    

def buffer(m):
    """Buffers Packets that are recieved ahead of order"""
    global bufferlist

    entry = (int(m.group(3)),int(m.group(5)),m.group(10),m.group(1))
    if entry not in bufferlist:
        bufferlist.append(entry)


def createLog (m,tag):
    """Creates the output log required by the assignment"""
    t = (time.strftime("%a %b %d %H:%M:%S %Z %Y: ",time.localtime()))
    print (t + "%s; %s; Sequence: %s; Length: %s; Acknowledgment: %s; Window: %s;" % (tag, m.group(1), m.group(3), m.group(5), m.group(7), m.group(9)))
 

if __name__ == '__main__':
    main()  