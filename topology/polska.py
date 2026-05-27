#!/usr/bin/python

from mininet.topo import Topo
from mininet.link import TCLink

def int2dpid( dpid ):
        try:
            dpid = hex( dpid )[ 2: ]
            dpid = '0' * ( 16 - len( dpid ) ) + dpid
            return dpid
        except IndexError:
            raise Exception( 'Unable to derive default datapath ID - '
                             'please either specify a dpid or use a '
                             'canonical switch name such as s23.' )

class Polska( Topo ):
    def __init__( self ):
        "Create custom topo."

        # Initialize topology
        Topo.__init__( self )
        # Add hosts and switches
        Gdansk = self.addSwitch('Gdansk',dpid=int2dpid(1))
        Bydgoszcz = self.addSwitch('Bydgoszcz',dpid=int2dpid(2))
        Kolobrzeg = self.addSwitch('Kolobrzeg',dpid=int2dpid(3))
        Katowice = self.addSwitch('Katowice',dpid=int2dpid(4))
        Krakow = self.addSwitch('Krakow',dpid=int2dpid(5))
        Bialystok = self.addSwitch('Bialystok',dpid=int2dpid(6))
        Lodz = self.addSwitch('Lodz',dpid=int2dpid(7))
        Poznan = self.addSwitch('Poznan',dpid=int2dpid(8))
        Rzeszow = self.addSwitch('Rzeszow',dpid=int2dpid(9))
        Szczecin = self.addSwitch('Szczecin',dpid=int2dpid(10))
        Warsaw = self.addSwitch('Warsaw',dpid=int2dpid(11))
        Wroclaw = self.addSwitch('Wroclaw',dpid=int2dpid(12))



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

        h_Gdansk = self.addHost('h_Gdansk')
        h_Bydgoszcz = self.addHost('h_Bydg')
        h_Kolobrzeg = self.addHost('h_Kolob')
        h_Katowice = self.addHost('h_Katowice')
        h_Krakow = self.addHost('h_Krakow')
        h_Bialystok = self.addHost('h_Bialyst')
        h_Lodz = self.addHost('h_Lodz')
        h_Poznan = self.addHost('h_Poznan')
        h_Rzeszow = self.addHost('h_Rzeszow')
        h_Szczecin = self.addHost('h_Szczecin')
        h_Warsaw = self.addHost('h_Warsaw')
        h_Wroclaw = self.addHost('h_Wroclaw')

        self.addLink(h_Gdansk, Gdansk, cls=TCLink, bw=1000)
        self.addLink(h_Bydgoszcz, Bydgoszcz, cls=TCLink, bw=1000)
        self.addLink(h_Kolobrzeg, Kolobrzeg, cls=TCLink, bw=1000)
        self.addLink(h_Katowice, Katowice, cls=TCLink, bw=1000)
        self.addLink(h_Krakow, Krakow, cls=TCLink, bw=1000)
        self.addLink(h_Bialystok, Bialystok, cls=TCLink, bw=1000)
        self.addLink(h_Lodz, Lodz, cls=TCLink, bw=1000)
        self.addLink(h_Poznan, Poznan, cls=TCLink, bw=1000)
        self.addLink(h_Rzeszow, Rzeszow, cls=TCLink, bw=1000)
        self.addLink(h_Szczecin, Szczecin, cls=TCLink, bw=1000)
        self.addLink(h_Warsaw, Warsaw, cls=TCLink, bw=1000)
        self.addLink(h_Wroclaw, Wroclaw, cls=TCLink, bw=1000)

topos = { 'polska': ( lambda: Polska() ) }

