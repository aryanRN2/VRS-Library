from collections import deque

class Solution:
    def minJumps(self, nums: list[int]) -> int:
        n = len(nums)
        if n <= 1:
            return 0
        
        mv = max(nums)
        
        # 1. Sieve of Eratosthenes to identify primes
        prim = [True] * (mv + 1)
        prim[0] = prim[1] = False
        for p in range(2, int(mv**0.5) + 1):
            if prim[p]:
                for i in range(p * p, mv + 1, p):
                    prim[i] = False
        
        # 2. Map primes to indices of their multiples
        # pi[p] = [indices j where nums[j] % p == 0]
        pi = {}
        for idx, val in enumerate(nums):
            # For each value, find its prime factors to populate the map
            # Optimization: only need to check primes up to sqrt(val)
            d = 2
            temp = val
            while d * d <= temp:
                if temp % d == 0:
                    if prim[d]:
                        pi.setdefault(d, []).append(idx)
                    while temp % d == 0:
                        temp //= d
                d += 1
            if temp > 1 and prim[temp]:
                pi.setdefault(temp, []).append(idx)

        # 3. BFS
        queue = deque([(0, 0)]) # (current_index, distance)
        visited = {0}
        # Keep track of which primes we've already "used" for teleportation
        usedd = set()

        while queue:
            ci, dist = queue.popleft()
            
            if ci == n - 1:
                return dist
            
            # ngh options
            nghs = []
            
            # Rule 1: Adjacent steps
            if ci + 1 < n: nghs.append(ci + 1)
            if ci - 1 >= 0: nghs.append(ci - 1)
            
            # Rule 2: Prime Teleportation
            val = nums[ci]
            if prim[val] and val not in usedd:
                if val in pi:
                    nghs.extend(pi[val])
                usedd.add(val)
            
            for ngh in nghs:
                if ngh not in visited:
                    visited.add(ngh)
                    queue.append((ngh, dist + 1))
                    if ngh == n - 1:
                        return dist + 1
        
        return -1