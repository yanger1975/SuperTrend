import numpy as np
from numba import njit

@njit
def kmeans_1d_labels(data: np.ndarray, k: int, max_iter: int = 100):
    """
    1D K-Means Clustering optimized with Numba.
    Returns: (centroids, labels)
    """
    n = len(data)
    if n == 0:
        return np.zeros(k), np.zeros(0, dtype=np.int32)
    
    # Initialize centroids based on percentiles
    centroids = np.zeros(k)
    if k == 3:
        centroids[0] = np.percentile(data, 25)
        centroids[1] = np.percentile(data, 50)
        centroids[2] = np.percentile(data, 75)
    elif k == 2:
        centroids[0] = np.percentile(data, 33)
        centroids[1] = np.percentile(data, 66)
    elif k == 1:
        centroids[0] = np.percentile(data, 50)
    else:
        for j in range(k):
            centroids[j] = np.percentile(data, (j + 1) * 100 / (k + 1))
        
    labels = np.zeros(n, dtype=np.int32)
    
    for _ in range(max_iter):
        # Assign points to closest centroid
        for i in range(n):
            val = data[i]
            min_dist = np.inf
            closest_k = 0
            for j in range(k):
                dist = abs(val - centroids[j])
                if dist < min_dist:
                    min_dist = dist
                    closest_k = j
            labels[i] = closest_k
            
        # Update centroids
        new_centroids = np.zeros(k)
        counts = np.zeros(k)
        for i in range(n):
            new_centroids[labels[i]] += data[i]
            counts[labels[i]] += 1
            
        for j in range(k):
            if counts[j] > 0:
                new_centroids[j] /= counts[j]
            else:
                new_centroids[j] = centroids[j]
                
        # Check convergence with tolerance
        same = True
        for j in range(k):
            if abs(centroids[j] - new_centroids[j]) > 1e-8:
                same = False
                break
                
        if same:
            break
            
        for j in range(k):
            centroids[j] = new_centroids[j]
            
    return centroids, labels
