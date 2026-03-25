import numpy as np
from scipy.ndimage import gaussian_filter

def generate_blue_noise_mask(size=256, sigma=1.5):
    """
    Void-and-Cluster implementation to create a toroidal Blue Noise Mask.
    """
    # 1. Start with a sparse random seed
    mask = np.zeros((size, size), dtype=float)
    n_points = (size * size) // 10
    indices = np.random.choice(size * size, n_points, replace=False)
    mask.ravel()[indices] = 1.0
    
    # 2. Rank array to store the order of points
    rank_mask = np.zeros((size, size), dtype=int)
    
    # Simple Void-and-Cluster approximation
    # In a full impl, you'd swap points to minimize energy.
    # For a scan strategy, even a Gaussian-filtered dither is excellent.
    for i in range(size * size):
        # Apply Gaussian filter to find 'clusters' (high density)
        # mode='wrap' ensures the mask is tileable (toroidal)
        density = gaussian_filter(mask, sigma=sigma, mode='wrap')
        
        if i < n_points: # Phase: Remove clusters
            idx = np.argmax(density * mask)
        else: # Phase: Fill voids
            idx = np.argmin(density + mask * 1e6)
            
        y, x = divmod(idx, size)
        mask[y, x] = 1.0 if i >= n_points else 0.0
        rank_mask[y, x] = i
        
    # Normalize to 0.0 - 1.0
    return rank_mask / (size * size)

# Generate and save
blue_noise_data = generate_blue_noise_mask(512) 
np.save('blue_noise_mask_512.npy', blue_noise_data)
print("Mask saved successfully!")
