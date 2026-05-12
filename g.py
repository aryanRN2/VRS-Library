class Solution:
    def kEffort(self, tasks: list[list[int]]) -> int:
        
        tasks.sort(key=lambda x: x[1] - x[0], reverse=True)
        
        a = 0
        it = 0
        
        for i, k in tasks:
            
            if a < k:
                
                it += (k - a)
                
                a = k
            
           
            a -= i
            
        return it