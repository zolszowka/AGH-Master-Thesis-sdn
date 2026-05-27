#!/usr/bin/python

from mininet.topo import Topo
from mininet.link import TCLink


def int2dpid(dpid):
    try:
        dpid = hex(dpid)[2:]
        dpid = '0' * (16 - len(dpid)) + dpid
        return dpid
    except IndexError:
        raise Exception('Unable to derive default datapath ID - '
                        'please either specify a dpid or use a '
                        'canonical switch name such as s23.')


class Polska(Topo):
    def __init__(self):
        "Create custom topo."

        # Initialize topology
        Topo.__init__(self)
        # Add hosts and switches
        Gdansk = self.addSwitch('Gdansk', dpid=int2dpid(1))
        Bydgoszcz = self.addSwitch('Bydgoszcz', dpid=int2dpid(2))
        Kolobrzeg = self.addSwitch('Kolobrzeg', dpid=int2dpid(3))
        Katowice = self.addSwitch('Katowice', dpid=int2dpid(4))
        Krakow = self.addSwitch('Krakow', dpid=int2dpid(5))
        Bialystok = self.addSwitch('Bialystok', dpid=int2dpid(6))
        Lodz = self.addSwitch('Lodz', dpid=int2dpid(7))
        Poznan = self.addSwitch('Poznan', dpid=int2dpid(8))
        Rzeszow = self.addSwitch('Rzeszow', dpid=int2dpid(9))
        Szczecin = self.addSwitch('Szczecin', dpid=int2dpid(10))
        Warsaw = self.addSwitch('Warsaw', dpid=int2dpid(11))
        Wroclaw = self.addSwitch('Wroclaw', dpid=int2dpid(12))

        self.addLink(Gdansk, Warsaw, cls=TCLink, bw=100)
        self.addLink(Gdansk, Kolobrzeg, cls=TCLink, bw=100)
        self.addLink(Bydgoszcz, Kolobrzeg, cls=TCLink, bw=100)
        self.addLink(Bydgoszcz, Poznan, cls=TCLink, bw=100)
        self.addLink(Bydgoszcz, Warsaw, cls=TCLink, bw=100)
        self.addLink(Kolobrzeg, Szczecin, cls=TCLink, bw=100)
        self.addLink(Katowice, Krakow, cls=TCLink, bw=100)
        self.addLink(Katowice, Lodz, cls=TCLink, bw=100)
        self.addLink(Katowice, Wroclaw, cls=TCLink, bw=100)
        self.addLink(Krakow, Rzeszow, cls=TCLink, bw=100)
        self.addLink(Krakow, Warsaw, cls=TCLink, bw=100)
        self.addLink(Bialystok, Rzeszow, cls=TCLink, bw=100)
        self.addLink(Bialystok, Warsaw, cls=TCLink, bw=100)
        self.addLink(Lodz, Warsaw, cls=TCLink, bw=100)
        self.addLink(Lodz, Wroclaw, cls=TCLink, bw=100)
        self.addLink(Poznan, Szczecin, cls=TCLink, bw=100)
        self.addLink(Poznan, Wroclaw, cls=TCLink, bw=100)
        self.addLink(Gdansk, Bialystok, cls=TCLink, bw=100)

        h_Gdansk = self.addHost(
            'h_Gdansk', mac='00:00:00:00:01:01', ip='10.0.0.1')
        h_Rzeszow = self.addHost(
            'h_Rzeszow', mac='00:00:00:00:02:02', ip='10.0.0.2')
        h_Wroclaw = self.addHost(
            'h_Wroclaw', mac='00:00:00:00:03:03', ip='10.0.0.3')
        h_Szczecin = self.addHost(
            'h_Szczecin', mac='00:00:00:00:04:04', ip='10.0.0.4')

        self.addLink(h_Gdansk, Gdansk, cls=TCLink, bw=1000)
        self.addLink(h_Rzeszow, Rzeszow, cls=TCLink, bw=1000)
        self.addLink(h_Wroclaw, Wroclaw, cls=TCLink, bw=1000)
        self.addLink(h_Szczecin, Szczecin, cls=TCLink, bw=1000)


topos = {'polska': (lambda: Polska())}
