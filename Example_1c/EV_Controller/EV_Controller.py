# -*- coding: utf-8 -*-
"""
Created on Thu Oct 11 10:08:26 2018

@author: monish.mukherjee
"""
import scipy.io as spio
from pypower.api import case118, ppoption, runpf, runopf
import math
import numpy
import copy
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime, timedelta
import time
import helics as h
import random
import logging
import json
import sys
import os
import pandas as pd

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

def create_broker():
    initstring = "2 --name=mainbroker"
    broker = h.helicsCreateBroker("zmq", "", initstring)
    isconnected = h.helicsBrokerIsConnected(broker)

    if isconnected == 1:
        pass

    return broker

def destroy_federate(fed):
    status = h.helicsFederateFinalize(fed)

    status, state = h.helicsFederateGetState(fed)
    assert state == 3

    #while (h.helicsBrokerIsConnected(broker)):
        #time.sleep(1)

    h.helicsFederateFree(fed)
    h.helicsCloseLibrary()


if __name__ == "__main__":

    # broker = create_broker()
    #fed = create_federate()

#################################  Registering  federate from json  ########################################
    
    fed = h.helicsCreateCombinationFederateFromJson('Control.json')
    status = h.helicsFederateRegisterInterfaces(fed, 'Control.json')
    federate_name = h.helicsFederateGetName(fed)[-1]
    print(federate_name)
    #print(" Federate {} has been registered".format(federate_name))
    endpoint_count = h.helicsFederateGetEndpointCount(fed)
    subkeys_count = h.helicsFederateGetSubscriptionCount(fed)
    print(subkeys_count)
    print(endpoint_count)
######################   Reference to Publications and Subscription form index  #############################   
    endid = {}
    subid = {}
    for i in range(0,endpoint_count):
        endid["m{}".format(i)] = h.helicsFederateGetEndpointByIndex (fed, i)
        end_name = h.helicsEndpointGetName(endid["m{}".format(i)])[1]
        print( 'Registered Endpoint ---> {}'.format(end_name))

    for i in range(0,subkeys_count):
        subid["m{}".format(i)] = h.helicsFederateGetSubscriptionByIndex(fed, i)
        status = h.helicsSubscriptionSetDefaultComplex(subid["m{}".format(i)], 0, 0)
        sub_key = h.helicsSubscriptionGetKey(subid["m{}".format(i)])[1]
        print( 'Registered Subscription ---> {}'.format(sub_key))
        
    print( '###############################################################################################')
    print( '########################   Entering Execution Mode  ##########################################')
######################   Entering Execution Mode  ##########################################################    
    h.helicsFederateEnterExecutionMode(fed)

    hours = 24
    total_inteval = int(60 * 60 * hours)
    grantedtime = -1
    update_interval = 5*60 
    feeder_limit_upper = 4 * (1000*1000)
    feeder_limit_lower = 2.7 * (1000*1000)
    k = 0
    data ={};
    time_sim = []; feeder_real_power = []; feeder_imag_power = []
    for t in range(0, total_inteval, update_interval):
        
        while grantedtime < t:
            status, grantedtime = h.helicsFederateRequestTime (fed, t)
        time.sleep(0.1)
        
        time_sim.append(t/3600)
        #############################   Subscribing to Feeder Load from to GridLAB-D ##############################################   
        key =[]; Real_demand = []; Imag_demand = []; 
        for i in range(0,subkeys_count):
            sub = subid["m{}".format(i)]        
            status, rload, iload = h.helicsSubscriptionGetComplex(sub)
            sub_key = h.helicsSubscriptionGetKey(sub)[1]
              
            if "totalLoad" in str(sub_key):
                key_feeder_load = sub_key
                distribution_fed_name =  str(key_feeder_load.split('/totalLoad')[0])
                Real_feeder_load = rload
                Imag_feeder_load = iload
                feeder_real_power.append(rload/1000)
                feeder_imag_power.append(iload/1000)
            else: 
                try:
                    data[sub_key].append(rload/1000)
                except KeyError:
                    data[sub_key] = [rload/1000]
                
                key.append(sub_key)
                Real_demand.append(rload)
                Imag_demand.append(iload)
             
        logger.info("EV Controller grantedtime = {}".format(grantedtime))
       
        
        logger.info('Total Feeder Load is {} + {} j'.format(Real_feeder_load, Imag_feeder_load))
        
        if (Real_feeder_load > feeder_limit_upper):
            logger.info('Total Feeder Load is over the Feeder Upper Limit')
            logger.info('Warning ----> Feeder OverLimit --->  Turn off EV')
            
            if (k < endpoint_count):   
                end = endid["m{}".format(k)]
                end_name = str(h.helicsEndpointGetName(end)[1])
                destination_name = (end_name.replace(federate_name, distribution_fed_name))
                print('Endpoint Destination {}'.format(destination_name))
                status = h.helicsEndpointSendMessageRaw(end, destination_name, str('0 + 0 j'))
                #status = h.helicsEndpointSendMessageRaw(end, 'NULL', str('0 + 0 j'))
                logger.info('Turning off {}'.format(end_name))
                k=k+1
            else:
                 logger.info('All EVs are Turned off')
        
        if  (Real_feeder_load < feeder_limit_lower):
            logger.info('Total Feeder Load is under the Feeder Lower Limit')
            logger.info('Feeder Can Support EVs ------>  Turn on EV')
            if (k > 0):
                k=k-1
                end = endid["m{}".format(k)]
                end_name = h.helicsEndpointGetName(end)[1]
                destination_name = (end_name.replace(federate_name,distribution_fed_name))
                print('Endpoint Destination {}'.format(destination_name))
                status = h.helicsEndpointSendMessageRaw(end, destination_name, str('200000 + 0 j'))
                #status = h.helicsEndpointSendMessageRaw(end, 'NULL', str('200000 + 0 j'))
                logger.info('Turning on {}'.format(end_name))
            else:
                logger.info('All EVs are Turned on')
        
    fig = plt.figure()
    fig.subplots_adjust(hspace=0.4, wspace=0.4)
    i = 1
    for keys in data:
        ax = fig.add_subplot(2, 3, i)
        ax.plot(time_sim, data[keys])
        ax.set_ylabel('EV Output in kW')
        ax.set_xlabel('Time ')
        ax.set_title(keys)
        i=i+1
    
    plt.show(block=True)   
    data['time'] = time_sim
    data['feeder_load(real)'] = feeder_real_power
    pd.DataFrame.from_dict(data=data).to_csv('EV_Outputs.csv', header=True)
    
    t = 60 * 60 * 24
    while grantedtime < t:
        status, grantedtime = h.helicsFederateRequestTime (fed, t)
    logger.info("Destroying federate")
    destroy_federate(fed)