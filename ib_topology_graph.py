#!/usr/bin/python
""" infiniband_topo_map.py

v1.0 April 29, 2015

Copyright 2015 Blake Caldwell
Oak Ridge National Laboratory
 
Purpose: Map out the IB topology
Where/How/When: Run from CLI
Return Values: 1 on success, 0 on unexpected failure
Expected Output: 
1) with -t or --tree a JSON file in hierarcal structure
   (parent-child) relationship
2) with -g or --graph a JSON file in links-nodes format
   with the links defined between nodes
3) with -d --dot FILE, create a JPEG names FILE using the
   pydot library (must be installed separately)

This program is licensed under GNU GPLv3. Full license in LICENSE


"""

#__email__ = 

debug = True

import sys
from optparse import OptionParser, OptionError
from operator import itemgetter

import re,os

def cleanDescr(descr):
    # only call strip methods if desc is not None
    if descr:
      descr = descr.lstrip()
      descr = descr.rstrip()
      descr = descr.lstrip("\'")
      descr = descr.rstrip("\'")
    else:
      descr = "   [Unused]"
    return descr

class Port(object):
    def __init__(self, portNum, lid, width, speed, parentType, parentGuid, parentDescr):
        self.portNum=portNum
        self.lid=lid
        self.speed=speed
        self.width=width
        self.remotePort=None
        self.parent=None
        self.errors={}
        self.parentType = parentType
        self.parentGuid = parentGuid
        self.parentDescr = parentDescr
    def addRemotePort(self,remotePort):
        self.remotePort=remotePort
    def addParent(self,parent):
        self.parent = parent
    def printPort(self):
        print "local lid: %s"%self.lid
        print "local port number: %s"%self.portNum
        print "local node guid: %s"%self.parentGuid
        print "local node description: %s"%self.parentDescr
        if self.remotePort:
            print "remote lid: %s"%self.remotePort.lid
            print "remote port number: %s"%self.remotePort.portNum
            print "remote guid: %s"%self.remotePort.parentGuid
            print "remote node description: %s"%self.remotePort.parentDescr
            print "width: %s"%self.width
            print "speed: %s"%self.speed
        else:
            print "remote port: None"
    def checkForErrors(self,errorKey,threshold):
        if threshold == None:
            threshold = 0
        try:
            if self.errors[errorKey] > threshold:
                return True
        except KeyError:
            pass
        return False

class Node(object):
    '''
    A Node is a collection of ports
    '''
    def __init__(self,descr,guid):
        self.guid=guid
        self.descr=cleanDescr(descr)
        self.ports={}
       
class switchNode(Node):
    ''' Switch nodes have ports that are all connected '''
    def __init__(self, guid, descr):
        self.subSwitches = {}
        self.hosts={}
        self.guid=guid
        self.descr=cleanDescr(descr)
        self.ports={}
    def addHCA(self,newHCA):
        self.hosts[newHCA.descr] = newHCA
    def addSwitch(self,newSwitch):
        self.subSwitches[newSwitch.descr] = newSwitch

class HCANode(Node):
    def __init__(self, guid, descr):
        super(HCANode,self).__init__(guid, descr)

class chassisSwitch:
    def __init__(self,descr):
        self.spines = {}
        self.leafs = {}
        self.descr=cleanDescr(descr)
    def addSpine(self,newSpine):
        self.spines[newSpine.guid] = newSpine
    def addLeaf(self,newLeaf):
        self.leafs[newLeaf.guid] = newLeaf

class Topology:
    global debug
    def __init__(self):
        self.chassisSwitches = {}
        self.switches = {}
        self.HCAs = {}
    def addChassisSwitch(self,newChassisSwitch):
        self.chassisSwitches[newChassisSwitch.descr] = newChassisSwitch
        # need to remove spines and leafs from switches dictionary
    def build(self,portList):
        for port in portList.ports:
            self._addPort(port)
            #self._addPort(port.remotePort)
    def _addPort(self, port):
        if port.parentType == "SW":
            myNode = switchNode(port.parentGuid, port.parentDescr)
            myNode.ports[port.portNum] = port
            port.addParent=myNode
            self._addSwitch(myNode)
        elif port.parentType == "CA":
            myNode = HCANode(port.parentGuid, port.parentDescr)
            myNode.ports[port.portNum] = port
            port.addParent=myNode
            self._addHCA(myNode)
        else:
            print "Unrecognized type: %s" % port.parentType
            return
            
    def _addSwitch(self,newSwitch):
        # If the switch already isn't in the topology
        if newSwitch.guid not in self.switches:
            self.switches[newSwitch.guid] = newSwitch
        else:
            # only need to add another port
            # since newSwitch will only have a single port, just add that one
            if debug:
                if len(newSwitch.ports) > 1:
                    print "There should only be one port in newly created switch!"
                    raise KeyError
            port_keys = newSwitch.ports.keys()
            only_port = port_keys[0]
            if debug:
                if only_port in self.switches[newSwitch.guid].ports:
                    print "This port is being added twice"
                    newSwitch.ports[only_port].printPort()
                    raise BaseException
            self.switches[newSwitch.guid].ports[only_port] = newSwitch.ports[only_port]
            
    def _addHCA(self,newHCA):
        if newHCA.guid not in self.HCAs:
            self.HCAs[newHCA.guid] = newHCA
        else:
            # only need to add another port
            if debug:
                if len(newHCA.ports) > 1:
                    print "There should only be one port in newly created HCA!"
                    raise KeyError
            port_keys = newHCA.ports.keys()
            only_port = port_keys[0]
            if debug:
                if only_port in self.HCAs[newHCA.guid].ports:
                    print "This port is being added twice"
                    newHCA.ports[only_port].printPort()
                    raise BaseException
            self.HCAs[newHCA.guid].ports[only_port] = newHCA.ports[only_port]

            # only need to add another port
    def printSwitches(self):
        for switch_guid in self.switches.iterkeys():
            print "Switch: %s" % (self.switches[switch_guid].descr)
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                print "[%d] %s port %d " % (int(index),myPort.remotePort.parentDescr,int(myPort.remotePort.portNum))
            print

    def createDot(self, output_file, cluster = None):
        graph = pydot.Dot(graph_type='graph',size="500, 300", ratio="expand",mode="major")
        #    cluster_XXX=pydot.Cluster('yyyy',label="zzz")

        for switch_guid in self.switches:
            # we only need to go through each switch and print all of the connected nodes

            switch_descr = self.switches[switch_guid].descr
            switch_descr = uniqueDescr(switch_descr,switch_guid)
            node_switch=pydot.Node("%s" % switch_descr)
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                node_descr=myPort.remotePort.parentDescr
                node_descr = uniqueDescr(node_descr,imyport.remotePort.parentGuid)
                node=pydot.Node("%s" % node_descr)
                edge=pydot.Edge(node_switch,node)
                graph.add_edge(edge)
                #if re.match("XXXX",remotePort.descr):
                #    cluster_XXX.add_node(node)
                #else:
                edge=pydot.Edge(node_switch,node)
            graph.add_node(node_switch)

        #graph.add_subgraph(cluster_XXX)
        full_path = "%s" % (output_file)

        graph.write_jpeg(full_path,prog="neato")

    def createTree(self,output_file):
        import json
    
        rootDict = {}
        added_list = {}
        leftoverDict = {}

        root = None
        for switch_guid in self.switches.iterkeys():
            # find a spine
            if "Spine" in uniqueDescr(self.switches[switch_guid].descr,switch_guid):
                root=switch_guid
        if not root:
                root=switch_guid

        # start at the root
        rootDict = {
             "name": uniqueDescr(self.switches[root].descr,root)
        }
        rootDict['children'] = []
        print "root is %s" % rootDict['name']
        for index,myPort in sorted(self.switches[root].ports.items(),key=itemgetter(1),reverse=True):
            if not myPort.remotePort:
                # disconnected, so continue
                continue
            if myPort.remotePort.parentGuid in added_list:
                continue
            tempDict = {}
            tempDict['name'] = uniqueDescr(myPort.remotePort.parentDescr,myPort.remotePort.parentGuid)
            tempDict['children'] = []
            if myPort.remotePort.parentType == "SW":
                added_list[myPort.remotePort.parentGuid] = tempDict
            rootDict['children'].append(tempDict)
            print "adding to root: %s"% uniqueDescr(myPort.remotePort.parentDescr,myPort.remotePort.parentGuid)

        for switch_guid in self.switches.iterkeys():
            if switch_guid == root:
                continue
            if switch_guid in added_list:
                continue
            switch_descr = self.switches[switch_guid].descr
            switch_descr = uniqueDescr(switch_descr,switch_guid)
            thisDict = {}
            thisDict['name'] = switch_descr
            thisDict['children'] = []

            # add HCAS
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                elif myPort.remotePort.parentType == "CA":
                    hostDict = { 'name':  myPort.remotePort.parentDescr }
                    thisDict['children'].append(hostDict)

            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                elif myPort.remotePort.parentGuid in added_list:
                    # this remote port has already been added, slide ourselves under it's children
                    added_list[myPort.remotePort.parentGuid]['children'].append(thisDict)
                    added_list[switch_guid] = thisDict
                    print "adding %s to %s" %(thisDict['name'], myPort.remotePort.parentDescr)
                    break
            if not switch_guid in added_list:
               thisDict['children'] = {}
               leftoverDict[switch_guid] = thisDict
        
        moreleftoverDict = {}
        # Now go through the rest of the switches
        for switch_guid in leftoverDict.iterkeys():
            if switch_guid in added_list:
                continue
            switch_descr = self.switches[switch_guid].descr
            switch_descr = uniqueDescr(switch_descr,switch_guid)
            thisDict = {}
            thisDict['name'] = switch_descr
            thisDict['children'] = []
            # find ports that connect to a switch already added
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                elif myPort.remotePort.parentType == "CA":
                    hostDict = { 'name':  myPort.remotePort.parentDescr }
                    thisDict['children'].append(hostDict)
                elif myPort.remotePort.parentGuid in added_list:
                    print "adding %s" % switch_descr
                    # this remote port has already been added, slide ourselves under it's children
                    added_list[myPort.remotePort.parentGuid]['children'].append(thisDict)
                    added_list[switch_guid] = thisDict
                    break
            if not switch_guid in added_list:
                thisDict['children'] = {}
                moreleftoverDict[switch_guid] = thisDict

        print "length of leftover = %d" % len(moreleftoverDict)

        f = open(output_file, 'w')

        f.write(json.dumps(
        rootDict,
        sort_keys=True,
        indent=2,
        separators=(',', ': ')))
        f.close()
    def createGraph(self,output_file):
        import json
        complete_graph = {}
        complete_graph["nodes"] = []
        complete_graph["links"] = []
        node_map = {}
        group_map = {}
        group_counter = 0

        for switch_guid in self.switches.iterkeys():
            this_switch = {}
            switch_descr = self.switches[switch_guid].descr
            core_pattern=".*MellanoxIS5600-([0-9])+.*"
            m = re.match(core_pattern,switch_descr)
            # convert switch name to unique name after having matched against it

            switch_descr = uniqueDescr(switch_descr,switch_guid)

            if m:
                if m.group(1) in group_map:
                    this_switch["group"] = group_map[m.group(1)]
                else:
                    this_switch["group"] = len(group_map)
                    group_map[m.group(1)] = len(group_map)
                    group_counter += 1
            else:
                this_switch["group"] = len(group_map)
                group_map[switch_guid] = len(group_map)
                group_counter += 1

            # convert switch name to unique name
            this_switch["name"] = switch_descr
            this_switch["guid"] = switch_guid
            this_switch["size"] = 4

            complete_graph["nodes"].append(this_switch)
            
            # add this index to the node map for finding source and destination nodes below
            node_map[switch_guid] = len(node_map)
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                if myPort.remotePort.parentType == "SW":
                    #switches have already been added
                    continue
                # at this point, it's an HCA
                this_node = {}

                if isLeafSwitch(myPort.parentDescr):
                    this_node["group"] = group_map[myPort.parentGuid]

                this_node["name"] = myPort.remotePort.parentDescr
                this_node["guid"] = myPort.remotePort.parentGuid
                this_node["size"] = 4
                complete_graph["nodes"].append(this_node)
                node_map[myPort.remotePort.parentGuid] = len(node_map)

        # after the first pass, all nodes are part of the dictionary
        for switch_guid in self.switches.iterkeys():
            for index,myPort in sorted(self.switches[switch_guid].ports.items(),key=itemgetter(1),reverse=True):
                if not myPort.remotePort:
                    # disconnected, so continue
                    continue
                #if myPort.remotePort.parentType == "SW":
                    #if isGroupedSwitch(myPort.remotePort.parentDescr):
                    #    # if its a TOR switch, put this in its group
                    #    node_num = node_map[myPort.parentGuid]
                    #    print node_num
                    #    print myPort.remotePort.parentGuid
                    #    complete_graph["nodes"][node_num]["group"] = group_map[myPort.remotePort.parentGuid]

                node_descr = myPort.remotePort.parentDescr
                node_descr = uniqueDescr(node_descr,myPort.remotePort.parentGuid)
                this_link = {}
                this_link["source"] = node_map[myPort.parentGuid]
                this_link["target"] = node_map[myPort.remotePort.parentGuid]
#                this_link["value"] = 5
        	complete_graph["links"].append(this_link)
		
        f = open(output_file, 'w')
        complete_graph
        f.write(json.dumps(
        complete_graph,
        sort_keys=True,
        indent=2,
        separators=(',', ': ')))
        f.close()

def isLeafSwitch(descr):
    if "Infiniscale-IV Mellanox Technologies" in descr:
        return True
    else:
        return False

def isSpineSwitch(descr):
    if "Spine" in uniqueDescr(descr):
        return True
    else:
        return False

def isLineSwitch(descr):
    if "Line" in uniqueDescr(descr):
        return True
    else:
        return False

def uniqueDescr(descr,guid=""):
    """ Clean up description if possible or use supplied GUID for uniqueness """

    spine_pattern=".*(MellanoxIS5600-[0-9]+).*\/S([0-9]+)\/.*"
    line_pattern=".*(MellanoxIS5600-[0-9]+).*\/L([0-9]+)\/.*"

    if "Infiniscale-IV Mellanox Technologies" in descr:
        descr = "Mellanox TOR: " + guid
    elif "MellanoxIS5600" in descr:
        m = re.match(spine_pattern, descr)
        if m:
            descr = "%s Spine %s" % (m.group(1), m.group(2))
        else:
            j = re.match(line_pattern, descr)
            if j:
                descr = "%s Line %s" % (j.group(1), j.group(2))

    return descr

class portList:
    def __init__(self):
        self.ports = []
    def add(self,singlePort):
        self.ports.append(singlePort)
    def remove(self,singlePort):
        index = self.find(singlePort)
        if not index:
            print "Could not find port to remove with guid %s and number %d in port list"%(singlePort.guid,singlePort.portNum)
            raise
        self.ports.remove(index)
    def find(self,guid,port):
        for port in self.ports:
            if (port.guid == guid and port.portNum == port):
                return port
        return None

def update_errors_from_ibqueryerrors(errors_file,switch_list):
    global debug
    error_list = NodeList()
    try:
        infile = open(errors_file)
    except:
        print "Unkown error opening file: ", infile
        sys.exit(1)

    pattern="^\s+GUID\s+([0-9xa-f]+)\s+port\s+(\d+):\s+(.*)$"
    skip_pattern="^Errors for.*$"
    
    for line in infile:
        line=line.rstrip()
        if re.match(skip_pattern, line):
            continue
        m = re.match(pattern, line)
        if m:
            guid = m.group(1).replace("0x","0x000")
            portnum = m.group(2)
            error_string=m.group(3)
            errors = parseErrorStr(error_string)
            switch = switch_list.find(guid)
            if switch:
                if switch.portsByNum.has_key(portnum):
                    thisPort = switch.portsByNum[portnum]
                    switch.updatePortErrors(thisPort,errors)
                    error_list.add(thisPort)
                    print "adding port %s to error list" % thisPort.descr
                else:
                    print "Error: port %s does not exist on switch %s" % (portnum,switch.descr)
                    continue
            else:
                print "not doing anything for guid %s" % guid
    return error_list

def parseErrorStr(errorString):
    errors = {}
    errorList = errorString.split('] [')
    for errorCounter in errorList:
        (counterName,counterValue) = errorCounter.split(" == ")
        counterName=counterName.replace("[",'')
        counterValue=counterValue.replace("]",'')
        try:
            errors[counterName]+=int(counterValue)
        except KeyError:
            errors[counterName]=int(counterValue)
    return errors
    
def parse_netdiscover(ibnetdiscover_file):
    global debug
    try:
        topology_infile = open(ibnetdiscover_file)
    except:
        print "Unkown error opening file: ", ibnetdiscover_file
        sys.exit(1)

    # the active port pattern will have the descriptions within parenthesis
    active_port_pattern="^(.*)\((.*)\).*$"
    
    # the disconnected port will always be on a switch and the name of the switch will
    # be in single quotes
    disconn_port_pattern="^(SW.*)\'(.*)\'.*$"
    counter = 0
    port_list = portList()
    all_lines = topology_infile.readlines()
    for line in all_lines:
        active_port = None
        disconn_port = None
        active_port = re.match(active_port_pattern, line)
        if not active_port:
            disconn_port = re.match(disconn_port_pattern, line)

        if active_port:
            (type1, lid1, port1, guid1, width, rate, dash, type2, lid2, port2, guid2) = active_port.group(1).split()
            (description1,description2) = active_port.group(2).split(" - ")
            thisPort = Port(port1,lid1,width,rate,type1,guid1,description1)
            remotePort = Port(port2,lid2,width,rate,type2,guid2,description2)
            thisPort.addRemotePort(remotePort)
        elif disconn_port:
            (type1, lid1, port1, guid1, width, rate) = disconn_port.group(1).split()
            description1 = disconn_port.group(2)
            thisPort = Port(port1,lid1,width,rate,type1,guid1,description1)
        else:
            sys.stdout.write("*** No match found for line: %s ***")% line
            pass

        port_list.add(thisPort)

    return port_list


def main():
    """main subroutine"""
    usage = "usage: %prog [-pvh] [-c cluster] [-o output_dir] [-t tree_file] [-g graph_file] [-d dot_file] ibnetdiscover_file [ ibqueryerrors_file ]"
    
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--cluster",dest="cluster", help="Color highlight a cluster (DISABLED)")
    parser.add_option("-o", "--output-dir", dest="output", help="Image output directory")
    parser.add_option("-d", "--dot", dest="dot", help="Generate graphviz (DOT) diagram", action="count")
    parser.add_option("-t", "--tree", dest="tree", help="Generate JSON tree")
    parser.add_option("-g", "--graph", dest="graph", help="Generate JSON graph")

    parser.add_option("-p", "--print", help="print topology to stdout", action="count", dest="printout")
    parser.add_option("-v", "--verbose", help="Be verbose", action="count")

    try:
        (options, args) = parser.parse_args()
    except OptionError:
        parser.print_help()
        return 1
    
    if options.cluster:
        print "%s %s %s" % ("NOTICE: the --cluster option is disabled because it requires site",
                            "specific options. Please modify the source with cluster strings and enable",
                            "this option manually")
        print
        #cluster = options.cluster
    else:
        cluster = ''

    if options.output:
        output_dir=options.output
    else:
        output_dir='.'

    if len(args) >= 1:
        ports=parse_netdiscover(args[0])
        flat_topology = Topology()
        flat_topology.build(ports)
       
        if len(args) == 2:
            nodes_with_errors = update_errors_from_ibqueryerrors(args[1],nodes)
    else:
        print "ERROR: no ibnetdiscover file given"
        sys.exit(1)

    if options.printout:
        flat_topology.printSwitches()

    if options.dot:
        # NOTE: these modules must be found in the current directory
        sys.path.append("pydot-1.0.28")
        sys.path.append("pyparsing-1.5.7")
        import pydot

        dot_outputfile = ""
        if output_dir:
            dot_output_file = output_dir+'/'+options.dot
        flat_topology.createDot(dot_outputfile)

    if options.tree:
        tree_outputfile = ""
        if output_dir:
            tree_outputfile = output_dir+'/'+options.tree
        flat_topology.createTree(tree_outputfile)

    if options.graph:
        graph_outputfile = ""
        if output_dir:
            graph_outputfile = output_dir+'/'+options.graph
        flat_topology.createGraph(graph_outputfile)

if __name__ == "__main__":
    sys.exit(main())
