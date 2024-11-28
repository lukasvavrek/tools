#!/usr/bin/python3

def gcd(M, N):
    x = M
    y = N

    while x != y:
        if x > y:
            x -= y
        elif y > x:
            y -= x

    return x


print(f'gcd(200, 25) = {gcd(200, 25)}')
print(f'gcd(10, 45) = {gcd(10, 45)}')
print(f'gcd(1701, 3768) = {gcd(1701, 3768)}')
