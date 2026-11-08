#include <stdio.h>
#include "orders.h"

int main(int argc, char **argv)
{
    if (argc < 2) return 1;
    printf("customer=%s\ncount=%d\n", argv[1], order_count(argv[1]));
    return 0;
}
