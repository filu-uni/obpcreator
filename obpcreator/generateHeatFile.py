import obplib as obp
import numpy as np 
import os



def bezier_circle(beamPower = 3000.0, spotSize = 1200.0, speed = 9922222, midpoint = [0, 0], radius = 1):
    a, b, c = 1.00005507808, 0.55342925736, 0.99873327689
    curves = []
    for i in range(2):
        for j in range(2):
            control_coordinates = [[0, a], [b, c], [c, b], [a, 0]]
            control_coordinates = [np.multiply(control_coordinates[i], radius) for i in range(len(control_coordinates))] #scale with radius
            #mirroring the control points in the x and y plane to create the four parts
            if i == 1:
                control_coordinates = [[np.multiply(control_coordinates[i][0], -1), control_coordinates[i][1]] for i in range(len(control_coordinates))]
            if j == 1:
                control_coordinates = [[control_coordinates[i][0], np.multiply(control_coordinates[i][1], -1)]  for i in range(len(control_coordinates))]
            control_coordinates = [np.add(control_coordinates[i], midpoint) for i in range(len(control_coordinates))] #translate midpoint
            control_points = [obp.Point(control_coordinates[i][0], control_coordinates[i][1]) for i in range(len(control_coordinates))] #create Point objects
            curves.append(obp.Curve(control_points[0], control_points[1], control_points[2], control_points[3], speed = speed, bp = obp.Beamparameters(spot_size = spotSize, power = beamPower))) #create circle segments
    return curves

def createHeatFile(name,beampower,path):
    i = 700
    cur_2 = bezier_circle(radius=700.0,beamPower=beampower) #create a circle
    counter = 2
    while i <= 44100:
        i += 700
        cur_2 = cur_2 + bezier_circle(radius=i,speed=int(10000000-(77778*counter)))
        counter += 1
    save_file = os.path.join(path,name)
    obp.write_obp(cur_2,save_file)


createHeatFile("testheat.obp",100,"")
