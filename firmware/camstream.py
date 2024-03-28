#! /usr/bin/env python3

import socket
import time
from imutils.video import VideoStream
import imagezmq
import zmq
from time import sleep

def sender_start(connect_to=None):
    sender = imagezmq.ImageSender(connect_to=connect_to)
    sender.zmq_socket.setsockopt(zmq.LINGER, 0)  # prevents ZMQ hang on exit
    # NOTE: because of the way PyZMQ and imageZMQ are implemented, the
    #       timeout values specified must be integer constants, not variables.
    #       The timeout value is in milliseconds, e.g., 2000 = 2 seconds.
    sender.zmq_socket.setsockopt(zmq.RCVTIMEO, 5000)  # set a receive timeout
    sender.zmq_socket.setsockopt(zmq.SNDTIMEO, 5000)  # set a send timeout
    return sender

sender = sender_start(connect_to='tcp://192.168.10.111:5555')

picam = VideoStream(usePiCamera=True, resolution=(640, 480)).start()
time.sleep(2.0)  # allow camera sensor to warm up
while True:  # send images as stream until Ctrl-C
    image = picam.read()
    try:
        sender.send_image('submarine', image)
    except (zmq.ZMQError, zmq.ContextTerminated, zmq.Again):
        #print("trying to connect camera stream")
        if 'sender' in locals():
            sender.close()
            sleep(1)
        sender = sender_start(connect_to='tcp://192.168.10.111:5555')
