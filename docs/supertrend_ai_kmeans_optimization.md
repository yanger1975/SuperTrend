# SuperTrend AI KMeans Optimization

## 背景 (Background)
在原始 Pine Script 版本的 `SuperTrend AI` 實作中，K-Means 分群演算法是在「歷史資料範圍 (maxData) 內的**每一根 K 棒**」即時運算。
輸入特徵為各個乘數的歷史績效分數 (`perf`)，資料點數量等於乘數的總組數 (例如 `minMult`=1 到 `maxMult`=5，`step`=0.5，共 9 個資料點)。

在移植到 Python 回測系統的初期版本中，為了確保分群的正確性與演算法標準化，我們採用了 `scikit-learn` 的 `KMeans` 套件。
然而，`scikit-learn` 在面對極小量資料集 (9 個點) 且需要執行數以萬計次數 (每一根 K 棒) 的情境下，底層的初始化與參數檢查會產生龐大的效能瓶頸 (Overhead)。

## 未來最佳化方向 (Future Optimization)
若未來在全域參數優化 (Grid Search) 或是長天期歷史回測時，發現 K-Means 運算速度過慢，建議採取以下方案：

### 1. Numba JIT 編譯的輕量級 K-Means
- **作法**：手寫一個針對一維陣列 (1D Array) 的 K-Means 迴圈演算法，並使用 `@numba.njit` 修飾器。
- **優勢**：Numba 能將 Python 迴圈編譯為機器碼，對於純數學運算可提升 100x 以上的效能。且手寫邏輯可完全移除 `scikit-learn` 中對於 `n_clusters`, `random_state`, `tol` 等不必要的每次檢查開銷。
- **參考實作邏輯**：
  ```python
  from numba import njit
  import numpy as np

  @njit
  def kmeans_1d(data, k=3, max_iter=1000):
      # 1. 根據四分位數初始化中心點 (如同 Pine Script)
      q25 = np.percentile(data, 25)
      q50 = np.percentile(data, 50)
      q75 = np.percentile(data, 75)
      centroids = np.array([q25, q50, q75])
      
      for _ in range(max_iter):
          # 2. 計算距離並指派群組
          clusters = [[0.0 for _ in range(0)] for _ in range(k)]
          for val in data:
              idx = np.argmin(np.abs(val - centroids))
              clusters[idx].append(val)
              
          # 3. 更新中心點
          new_centroids = np.zeros(k)
          for i in range(k):
              if len(clusters[i]) > 0:
                  new_centroids[i] = np.mean(np.array(clusters[i]))
              else:
                  new_centroids[i] = centroids[i]
                  
          # 4. 檢查收斂
          if np.all(centroids == new_centroids):
              break
          centroids = new_centroids
          
      return centroids
  ```

### 2. 向量化 Numpy 運算 (Rolling Window)
- **作法**：將過去 N 天的所有績效分數轉換為矩陣，透過 `numpy` 的廣播機制 (Broadcasting) 整批計算距離，而不再依賴純 `for` 迴圈逐行執行。

### 3. 取樣頻率調整 (Downsampling)
- **作法**：由於績效分數 (`perf`) 是採用移動平均計算，數值變動平緩，分群中心不需要在「每 1 分鐘或每 1 天」都重新計算。可改為每 5 根或 10 根 K 棒執行一次 KMeans，並於期間內複用前一次的分群結果。

## 結論
當前系統先以 `scikit-learn` 作為功能驗證 (PoC) 與確保正確性的首選。上述三個方案可做為遇到實際效能瓶頸時的第一處理順位。
