from obpcreator.simple_input import SimpleBuild
import pyvista as pv
import os

cube1 = pv.Cube(center=(15,-15,5),x_length=10,y_length=10,z_length=10)
cube2 = pv.Cube(center=(15,0,5),x_length=10,y_length=10,z_length=10)
cube3 = pv.Cube(center=(15,15,5),x_length=10,y_length=10,z_length=10)
cube4 = pv.Cube(center=(0,-15,5),x_length=10,y_length=10,z_length=10)
cube5 = pv.Cube(center=(0,0,5),x_length=10,y_length=10,z_length=10)
cube6 = pv.Cube(center=(0,15,5),x_length=10,y_length=10,z_length=10)
cube7 = pv.Cube(center=(-15,-15,5),x_length=10,y_length=10,z_length=10)
cube8 = pv.Cube(center=(-15,0,5),x_length=10,y_length=10,z_length=10)
cube9 = pv.Cube(center=(-15,15,5),x_length=10,y_length=10,z_length=10)

build = SimpleBuild(
    meshes = [cube1],#[cube1, cube2, cube3, cube4, cube5, cube6, cube7],
    spot_size = [2000],
    beam_power = [660],
    scan_speed = [2031000],
    dwell_time = [515000],
    infill_strategy = ["point_random_stack"], #["line_concentric", "line_concentric", "line_spiral", "line_spiral", "line_snake", "point_random", "point_quasi_random"],
    infill_settings = [{'direction': 'inward'}, {'direction': 'outward'},{'direction': 'inward'}, {'direction': 'outward'}, {},{},{}],
    infill_point_distance = [2],
    layer_height = 0.4,
    rotation_angle = [0],
    )
build.prepare_build(os.getcwd(),gui=False)
