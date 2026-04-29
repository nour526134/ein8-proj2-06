import math
import random
import os
import sys
from pathlib import Path
if "SUMO_HOME" in os.environ:
    sys.path += [os.path.join(os.environ["SUMO_HOME"], "tools")]
else:
    sys.path += ["/usr/share/sumo/tools"]
    
import traci
import sumolib
import socket
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.gtfs_service import GTFSService
from rl.simulators.car_simulator import haversine_m

def find_free_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s :
        s.bind(("",0))
        return s.getsockname()[1]
        


class CarSimulator:

    def __init__(self,gui=False):

        BASE = os.path.dirname(os.path.abspath(__file__))
        self.sumocfg = os.path.join(BASE, "confing/simu.sumocfg")
        self.net = sumolib.net.readNet(os.path.join(BASE, "network/network.net.xml"))
        self.position_lat = None
        self.position_lon = None
        self._running = False
        self._time = 0.0
        self.dest_edge = None
        self.dest_id = None
        self.dist=0.0
        self.time_to_dest_min=0.0
        self._car_time_to_station_min = 0
        self.current_hour = 0.0
        self.rng = random.Random()
        self.closest_station_id = None
        self.dist_to_station_km = 0
        self.gtfs_service = GTFSService("data/gtfs_bordeaux")
        self.stations =self.gtfs_service.load_stops()
        self.gui=gui
        self.station={}
        self.port=find_free_port()
    
    def _is_car_alive(self) -> bool:
        # Vérifier si la voiture est encore dans la simulation
        # en utilisant traci.vehicle.getIDList() qui retourne la liste des véhicules présents
        return "C1" in traci.vehicle.getIDList()

    def reset(self, seed=None):
        print(f"[DEBUG] Début de l'épisode {self.episode_count}")
        if seed is not None:
            self.rng.seed(seed)

        if traci.isLoaded():
            traci.close()

        self.current_hour = self.rng.uniform(0.0, 24.0)
        self._time = int(self.current_hour * 3600)
        end_time = min(self._time + 7200, 24 * 3600)

        binary = "sumo-gui" if self.gui else "sumo"
        cmd = [binary, "-c", self.sumocfg, "--no-warnings", "--begin", str(self._time), "--end", str(end_time),"--remote-port",str(self.port)]
        traci.start(cmd)

        all_edges = traci.edge.getIDList()
        valid_edges = valid_edges = [e.getID() for e in self.net.getEdges() if e.allows("passenger") and not e.getID().startswith(":")]

        MAX_RETRIES = 20

        for _ in range(MAX_RETRIES):
            start_edge = self.rng.choice(valid_edges)
            dest_edge = self.rng.choice(valid_edges)

            if start_edge == dest_edge:
                continue

            route = traci.simulation.findRoute(start_edge, dest_edge)
 
            if not route.edges:
                continue

            traci.route.add("route_C1", list(route.edges))
            traci.vehicle.add(vehID="C1", routeID="route_C1", typeID="DEFAULT_VEHTYPE", depart="now", departLane="best")
            traci.vehicle.setColor("C1", (0, 255, 0, 255))  
            traci.simulationStep()
            self.position_lat, self.position_lon = traci.vehicle.getPosition("C1")
            if(self.gui):
                traci.gui.setOffset("View #0", self.position_lat, self.position_lon)
                traci.gui.setZoom("View #0", 1000)  

            self.dest_edge = dest_edge
            self.dist = route.length / 1000 
            self.time_to_dest_min=route.travelTime / 60
            self.current_saturation = traci.edge.getLastStepOccupancy(start_edge)
            speed = traci.edge.getLastStepMeanSpeed(start_edge)
            self._update_dist_to_station()
            return

        raise RuntimeError(f"Aucun chemin valide après {MAX_RETRIES} tentatives")




    def _update_dist_to_station(self):
        if not self._is_car_alive():
            return
        x, y = traci.vehicle.getPosition("C1")
        lon, lat = self.net.convertXY2LonLat(x, y)

        min_dist = float("inf")
        closest_id = None

        # itérer sur items()
        for sid, sdata in self.stations.items():
            dist = haversine_m(lat, lon, sdata["lat"], sdata["lon"])
            if dist < min_dist:
                min_dist = dist
                closest_id = sid
                self.station = {
                    'id':  sid,
                    'lat':self.stations[sid]['lat'],
                    'lon': self.stations[sid]['lon'],
                }

        self.dist_to_station_km = min_dist / 1000.0
        self.closest_station_id = closest_id

        
    def advance(self, dt_min):
        dt_s = dt_min * 60
        for _ in range(int(dt_s)):
            if self._is_car_alive():
                x, y = traci.vehicle.getPosition("C1")
                if(self.gui):
                    traci.gui.setOffset("View #0", x, y)
            if not self._is_car_alive():
                break
            try:
                traci.simulationStep()

            except traci.exceptions.FatalTraCIError:
                break
        self._time += dt_s
        if self._is_car_alive():
            self._update_dist_to_station()
        
        
    

    def get_metrics(self) -> dict:
        return {
            "time_min": self.get_time_min(),
            "dist_to_station_km": self.dist_to_station_km,
            "dist_to_dest_km": self.dist,
            "traffic": self.current_saturation,
        }

    def get_dist_to_station_km(self) -> float:
        return self.dist_to_station_km

    def get_closest_station(self) -> str:
        return self.station
    
    def get_dest_id(self) -> str:
        return self.dest_id

    def get_time_min(self) -> float:
        return self._time/60 

    def car_time_to_dest(self) -> float:
        return self.time_to_dest_min

    def car_time_to_station(self) -> float:
        return self._car_time_to_station_min 

    def car_time_to_parking(self, parking: dict) -> float:
        x, y = self.net.convertLonLat2XY(parking['lon'], parking['lat'])
        edges = self.net.getNeighboringEdges(x, y, r=300)
        edges = [(e, d) for e, d in edges if e.allows("passenger")]
        parking_edge = min(edges, key=lambda e: e[1])[0].getID()
        stage = traci.simulation.findRoute(fromEdge = traci.vehicle.getRoadID("C1"),toEdge   = parking_edge ,vType    = "DEFAULT_VEHTYPE")
        return stage.travelTime / 60.0 # Convertir en minutes
    


if __name__ == "__main__":
    # Initialiser le simulateur
    print("Initialisation du simulateur...")
    sim = CarSimulator(gui=False)

    # Réinitialiser la simulation avec une graine spécifique
    print("Réinitialisation de la simulation...")
    try:
        sim.reset(seed=42)
    except RuntimeError as e:
        print(f"Erreur lors de la réinitialisation : {e}")
        sys.exit(1)

    # Afficher les informations initiales
    print("\nVoiture initialisée")
    print(f"Position lat/lon : {sim.position_lat}, {sim.position_lon}")
    print(f"Station la plus proche : {sim.get_closest_station()}")
    print(f"Distance à la station la plus proche : {sim.get_dist_to_station_km():.3f} km")
    print(f"Distance totale à la destination : {sim.dist:.3f} km")

    # Avancer la simulation de 5 minutes
    print("\nAvancer la simulation de 5 minutes...")
    sim.advance(dt_min=5)

    # Afficher les informations après 5 minutes
    print("\nAprès 5 minutes d'avance :")
    print(f"Position lat/lon : {sim.position_lat}, {sim.position_lon}")
    print(f"Distance restante à la destination : {sim.dist:.3f} km")

    # Avancer la simulation jusqu'à l'arrivée
    print("\nSimulation jusqu'à l'arrivée...")
    while sim._is_car_alive():
        sim.advance(dt_min=1)  # Avancer par incréments de 1 minute
        print(sim.get_metrics())

    print("\nLa voiture est arrivée à destination.")
    print("Métriques finales :")
    print(sim.get_metrics())