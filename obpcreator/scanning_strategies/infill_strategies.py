
import numpy as np
import obplib as obp
import shapely
from pathlib import Path

def find_start_end_line_positions(arr):
    arr = np.array(arr)
    left_zeros_positions = np.where((np.roll(arr, shift=1, axis=1) == 0) & (arr == 1))
    left_positions = [(r, c) for r, c in zip(*left_zeros_positions)]
    first_elements = np.where(arr[:, 0] == 1)
    left_positions.extend([(r, 0) for r in first_elements[0]])
    right_zeros_positions = np.where((np.roll(arr, shift=-1, axis=1) == 0) & (arr == 1))
    right_positions = [(r, c) for r, c in zip(*right_zeros_positions)]
    last_elements = np.where(arr[:, -1] == 1)
    right_positions.extend([(r, arr.shape[1]-1) for r in last_elements[0]])
    left_positions = sorted(list(set(left_positions)))
    right_positions = sorted(list(set(right_positions)))
    return left_positions, right_positions

def snake_sort(t):
    if t[0] % 2 == 0:  # if the first value is even
        return (t[0], t[1])
    else:  # if the first value is odd
        return (t[0], -t[1])

def right_sort(t):
    return (t[0], -t[1])

def line_snake(part, layer):
    scan_strategy_settings = part.infill_setting.strategy_settings
    short_as_point = False
    if 'short_as_point' in scan_strategy_settings:
        if scan_strategy_settings['short_as_point'] == 'true':
            short_as_point = True
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    left, right = find_start_end_line_positions(keep_matrix)
    snake_sorted_left = sorted(left, key=snake_sort)
    snake_sorted_right = sorted(right, key=snake_sort)
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for i in range(len(snake_sorted_left)):
        start_coord = coord_matrix[snake_sorted_left[i][0]][snake_sorted_left[i][1]]
        end_coord = coord_matrix[snake_sorted_right[i][0]][snake_sorted_right[i][1]]
        if start_coord==end_coord:
            if short_as_point:
                a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
                obp.Point(start_coord.real*1000, start_coord.imag*1000)
                obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
        else:
            a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
            b = obp.Point(end_coord.real*1000, end_coord.imag*1000)
            obp_elements.append(obp.Line(a,b,scan_settings.scan_speed,bp))
    return obp_elements

def line_left_right(part, layer):
    scan_strategy_settings = part.infill_setting.strategy_settings
    short_as_point = False
    if 'short_as_point' in scan_strategy_settings:
        if scan_strategy_settings['short_as_point'] == 'true':
            short_as_point = True
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    left, right = find_start_end_line_positions(keep_matrix)
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for i in range(len(left)):
        start_coord = coord_matrix[left[i][0]][left[i][1]]
        end_coord = coord_matrix[right[i][0]][right[i][1]]
        if start_coord==end_coord:
            if short_as_point:
                a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
                obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
        else:
            a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
            b = obp.Point(end_coord.real*1000, end_coord.imag*1000)
            obp_elements.append(obp.Line(a,b,scan_settings.scan_speed,bp))
    return obp_elements

def line_right_left(part, layer):
    scan_strategy_settings = part.infill_setting.strategy_settings
    short_as_point = False
    if 'short_as_point' in scan_strategy_settings:
        if scan_strategy_settings['short_as_point'] == 'true':
            short_as_point = True
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    left, right = find_start_end_line_positions(keep_matrix)
    snake_sorted_left = sorted(left, key=right_sort)
    snake_sorted_right = sorted(right, key=right_sort)
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for i in range(len(snake_sorted_left)):
        start_coord = coord_matrix[snake_sorted_left[i][0]][snake_sorted_left[i][1]]
        end_coord = coord_matrix[snake_sorted_right[i][0]][snake_sorted_right[i][1]]
        if start_coord==end_coord:
            if short_as_point:
                a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
                obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
        else:
            a = obp.Point(start_coord.real*1000, start_coord.imag*1000)
            b = obp.Point(end_coord.real*1000, end_coord.imag*1000)
            obp_elements.append(obp.Line(a,b,scan_settings.scan_speed,bp))
    return obp_elements

from obpcreator.visualisation.layer_vis import vis_keep_layer

def line_concentric(part, layer):
    scan_strategy_settings = part.infill_setting.strategy_settings
    inward = True
    if 'direction' in scan_strategy_settings:
        if scan_strategy_settings['direction'] == 'outward':
            inward = False
    scan_settings = part.infill_setting.beam_settings
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    offset_distance = part.point_geometry.coord_matrix[1,0,0,0] - part.point_geometry.coord_matrix[0,0,0,0]
    contours = part.point_geometry.get_contours(layer)
    obp_elements = []
    for contour in contours:
        line = contour
        while not line.is_empty:
            x, y = line.exterior.xy
            for i in range(len(x)-1):
                if not inward:
                    a = obp.Point(x[i]*1000, y[i]*1000)
                    b = obp.Point(x[i+1]*1000, y[i+1]*1000)
                else:
                    b = obp.Point(x[i]*1000, y[i]*1000)
                    a = obp.Point(x[i+1]*1000, y[i+1]*1000)
                obp_elements.append(obp.Line(a,b,scan_settings.scan_speed,bp))
            line = line.buffer(-offset_distance)
    if not inward:
        obp_elements = obp_elements[::-1]
    return obp_elements

def line_spiral(part, layer):
    def find_point(x1, y1, x2, y2, d):
        # Finding the point on the distance d from from x1, y1 in the direction towards x2, y2
        direction_vector = np.array([x2 - x1, y2 - y1])
        unit_vector = direction_vector / np.linalg.norm(direction_vector)
        scaled_vector = unit_vector * d
        x3, y3 = np.array([x1, y1]) + scaled_vector
        return x3, y3
    scan_strategy_settings = part.infill_setting.strategy_settings
    inward = True
    if 'direction' in scan_strategy_settings:
        if scan_strategy_settings['direction'] == 'outward':
            inward = False
    scan_settings = part.infill_setting.beam_settings
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    offset_distance = part.point_geometry.coord_matrix[1,0,0,0] - part.point_geometry.coord_matrix[0,0,0,0]
    contours = part.point_geometry.get_contours(layer)
    obp_elements = []
    for contour in contours:
        line = contour
        first = True
        x_end, y_end = 0, 0
        while not line.is_empty:
            x, y = line.exterior.xy
            if first:
                x_start, y_start = x[0], y[0]
                first = False
            else: 
                x_start, y_start = x_end, y_end
            x_end, y_end = find_point(x[-1], y[-1], x[-2], y[-2], offset_distance)
            x[0], y[0] = x_start, y_start
            x[-1], y[-1] = x_end, y_end
            for i in range(len(x)-1):
                if not inward:
                    a = obp.Point(x[i]*1000, y[i]*1000)
                    b = obp.Point(x[i+1]*1000, y[i+1]*1000)
                else:
                    b = obp.Point(x[i]*1000, y[i]*1000)
                    a = obp.Point(x[i+1]*1000, y[i+1]*1000)
                obp_elements.append(obp.Line(a,b,scan_settings.scan_speed,bp))
            line = line.buffer(-offset_distance)
    if not inward:
        obp_elements = obp_elements[::-1]
    return obp_elements

def point_random(part, layer):
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    selected_values = coord_matrix[keep_matrix == 1]
    np.random.shuffle(selected_values)
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for point in selected_values:
        a = obp.Point(point.real*1000, point.imag*1000)
        obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
    return obp_elements

def point_random_stack(part, layer):
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    selected_values = []
    if layer % 2 != 0: #every other layer
        # Find the coordinates where keep_matrix is 1
        coords = np.argwhere(keep_matrix == 1)
        # Determine the bounding box
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)

        # Crop both matrices to the shape of the ones
        keep_matrix = keep_matrix[y_min:y_max, x_min:x_max]
        coord_matrix = coord_matrix[y_min:y_max, x_min:x_max]

        # Apply your physical shift (0.5 * spot size)
        shift = (scan_settings.spot_size * 0.001 / 2) + 1j * (scan_settings.spot_size * 0.001 / 2)

        # Extract values where keep_matrix is 1 (within the new cropped shape)
        selected_values = coord_matrix[keep_matrix == 1]
        selected_values += shift
    else:
        selected_values = coord_matrix[keep_matrix == 1]
    np.random.shuffle(selected_values)
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for point in selected_values:
        a = obp.Point(point.real*1000, point.imag*1000)
        obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
    return obp_elements

def point_blue_noise_mask(part, layer):
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    
    mask_path = Path(__file__).resolve().parent / "blue_noise_mask_512.npy"
    # Load the pre-calculated rank mask
    mask = np.load(mask_path)
    mask_size = mask.shape[0]
    
    all_points = coord_matrix[keep_matrix == 1]
    x, y = all_points.real, all_points.imag
    
    # Mapping coordinates to the mask lacally
    # We use a scale factor to control the 'granularity' of the noise
    # Setting scale to the part's bounding box makes the noise 'global'
    # LOCAL MAPPING (Pattern stays same if part moves)
    x = x - np.min(x)
    y = y - np.min(y)
    
    # Tiling logic: map real-world mm to mask pixels
    # This ensures the blue noise pattern is consistent across all layers
    pixel_spacing = scan_settings.spot_size * 0.001 # mm per mask pixel
    
    # Add a shift based on the layer number to break up vertical patterns
    # zero for now for testing
    shift = 0#(layer * 131) % mask_size 
    u = (x / pixel_spacing + shift).astype(int) % mask_size
    v = (y / pixel_spacing + shift).astype(int) % mask_size
    
    # Assign ranks and sort
    ranks = mask[u, v]
    sorted_points = all_points[np.argsort(ranks)]
    
    # Build OBP
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for p in sorted_points:
        a = obp.Point(p.real * 1000, p.imag * 1000)
        obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
        
    return obp_elements


# distribution with a decent distance between each point
# further reading: https://extremelearning.com.au/unreasonable-effectiveness-of-quasirandom-sequences/
def point_quasi_random(part, layer):
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    selected_values = coord_matrix[keep_matrix == 1]

    def phi(d):
        x=2.0000
        for i in range(10):
            x = pow(1+x,1/(d+1))
        return x

    # number of required points
    n = len(selected_values)

    d = 1
    g = phi(d)
    alpha = np.zeros(d)
    for j in range(d):
        alpha[j] = pow(2/g,j+1) % 1
    z = np.zeros((n, d))

    # This number can be any real number.
    # Common default setting is typically seed = 0
    # But seed = 0.5 might be marginally better.

    seed = 0
    for i in range(n):
        z[i] = (seed + alpha*(i+1)) % 1
    z1 = np.array(z).flatten()

    selected_values = selected_values[(np.argsort(z1))]

    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for point in selected_values:
        a = obp.Point(point.real*1000, point.imag*1000)
        obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
    return obp_elements

def point_ordered(part, layer):
    def n_stack(keep_array, coord_array, n_to_stack, stack_row):
        num_rows = keep_array.shape[0]
        extended_shape = (num_rows, keep_array.shape[1] + n_to_stack)
        extended_keep = np.zeros(extended_shape, dtype=keep_array.dtype)
        extended_coord = np.zeros(extended_shape, dtype=coord_array.dtype)
        indices = np.arange(num_rows)
        start_stack = np.floor_divide(indices, stack_row) % 2 == 1
        end_stack = ~start_stack
        extended_keep[end_stack, :keep_array.shape[1]] = keep_array[end_stack]
        extended_coord[end_stack, :coord_array.shape[1]] = coord_array[end_stack]
        extended_keep[start_stack, n_to_stack:] = keep_array[start_stack]
        extended_coord[start_stack, n_to_stack:] = coord_array[start_stack]
        return extended_keep, extended_coord
    
    coord_matrix, keep_matrix = part.point_geometry.get_layer(layer)
    scan_settings = part.infill_setting.beam_settings
    scan_strategy_settings = part.infill_setting.strategy_settings
    x_jump = scan_strategy_settings["x_jump"]
    y_jump = scan_strategy_settings["y_jump"]

    new_keep, new_coord = n_stack(keep_matrix, coord_matrix, int(x_jump/2), y_jump)

    len_x = new_keep.shape[1]
    len_y = new_keep.shape[0]

    new_new_keep = new_keep.reshape(-1)
    new_new_coord = new_coord.reshape(-1)
    Y, X = np.meshgrid(np.arange(len_y), np.arange(len_x), indexing='ij')
    ordered_Y = np.concatenate([Y[i::y_jump, j::x_jump].flatten() for i in range(y_jump) for j in range(x_jump)])
    ordered_X = np.concatenate([X[i::y_jump, j::x_jump].flatten() for i in range(y_jump) for j in range(x_jump)])
    order = ordered_Y * len_x + ordered_X
    coords_reordered = new_new_coord[order]
    keep_reordered = new_new_keep[order]
    keep_bool = keep_reordered.astype(bool)
    filtered_coords2 = coords_reordered[keep_bool]
    
    obp_elements = []
    bp = obp.Beamparameters(scan_settings.spot_size, scan_settings.beam_power)
    for point in filtered_coords2:
        a = obp.Point(point.real*1000, point.imag*1000)
        obp_elements.append(obp.TimedPoints([a], [scan_settings.dwell_time], bp))
    return obp_elements
