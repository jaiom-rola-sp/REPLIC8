! ============================================================
! SUBSIDIARY C - PARTS INVENTORY AND LOGISTICS (PIL)
! Industrial logistics: replacement-part stock and shipping lanes.
! Demo stand-in for REPLIC8 (FR-10). Read-only lookups.
! Line protocol: command on line 1, KEY=VALUE lines, END.
! ============================================================
program inventory
  implicit none
  character(len=64) :: cmd, line, key
  character(len=40) :: val
  character(len=10) :: in_part, in_dest
  integer :: ios, guard, eq

  in_part = ' '
  in_dest = ' '
  read(*, '(A)', iostat=ios) cmd
  if (ios /= 0) error stop 1

  do guard = 1, 20
    read(*, '(A)', iostat=ios) line
    if (ios /= 0) exit
    if (trim(line) == 'END' .or. len_trim(line) == 0) exit
    eq = index(line, '=')
    if (eq == 0) cycle
    key = line(1:eq-1)
    val = line(eq+1:)
    select case (trim(key))
    case ('PART-ID')
      in_part = val
    case ('DESTINATION')
      in_dest = val
    end select
  end do

  select case (trim(cmd))
  case ('CHECK_STOCK')
    call check_stock(in_part)
  case ('GET_SHIPPING_OPTIONS')
    call get_shipping_options(in_part, in_dest)
  case default
    print '(A)', 'ERROR=UNKNOWN-COMMAND'
    error stop 2
  end select

contains

  ! Find a part in the stock file. Returns .true. and its fields when found.
  logical function find_part(part_id, desc, qty, warehouse)
    character(len=*), intent(in) :: part_id
    character(len=24), intent(out) :: desc
    integer, intent(out) :: qty
    character(len=10), intent(out) :: warehouse
    character(len=10) :: p
    integer :: u, ios

    find_part = .false.
    open(newunit=u, file='data/stock.dat', status='old', action='read', iostat=ios)
    if (ios /= 0) then
      print '(A)', 'ERROR=DATA-FILE-UNAVAILABLE'
      error stop 3
    end if
    do
      read(u, '(A10,A24,I5,A10)', iostat=ios) p, desc, qty, warehouse
      if (ios /= 0) exit
      if (trim(p) == trim(part_id)) then
        find_part = .true.
        exit
      end if
    end do
    close(u)
  end function find_part

  ! How many of a part are on hand, and where.
  subroutine check_stock(part_id)
    character(len=*), intent(in) :: part_id
    character(len=24) :: desc
    character(len=10) :: warehouse
    integer :: qty

    if (find_part(part_id, desc, qty, warehouse)) then
      print '(A)', 'FOUND=Y'
      print '(A)', 'PART-ID=' // trim(part_id)
      print '(A)', 'DESCRIPTION=' // trim(desc)
      print '(A,I0)', 'ON-HAND=', qty
      print '(A)', 'WAREHOUSE=' // trim(warehouse)
    else
      print '(A)', 'FOUND=N'
      print '(A)', 'PART-ID=' // trim(part_id)
    end if
  end subroutine check_stock

  ! Shipping lanes from the part's warehouse to a destination region.
  subroutine get_shipping_options(part_id, destination)
    character(len=*), intent(in) :: part_id, destination
    character(len=24) :: desc
    character(len=10) :: warehouse, wh, dest
    character(len=12) :: carrier
    character(len=12) :: cost_text
    integer :: qty, days, u, ios, count
    real :: cost

    count = 0
    if (.not. find_part(part_id, desc, qty, warehouse)) then
      print '(A)', 'FOUND=N'
      print '(A)', 'BEGIN-ITEMS'
      print '(A)', 'COUNT=0'
      return
    end if
    print '(A)', 'FOUND=Y'
    print '(A)', 'WAREHOUSE=' // trim(warehouse)
    print '(A)', 'DESTINATION=' // trim(destination)
    print '(A)', 'BEGIN-ITEMS'
    open(newunit=u, file='data/lanes.dat', status='old', action='read', iostat=ios)
    if (ios /= 0) then
      print '(A)', 'ERROR=DATA-FILE-UNAVAILABLE'
      error stop 3
    end if
    do
      read(u, '(A10,A10,A12,I3,F8.2)', iostat=ios) wh, dest, carrier, days, cost
      if (ios /= 0) exit
      if (trim(wh) == trim(warehouse) .and. trim(dest) == trim(destination)) then
        count = count + 1
        write(cost_text, '(F12.2)') cost
        print '(A)', 'CARRIER=' // trim(carrier)
        print '(A,I0)', 'TRANSIT-DAYS=', days
        print '(A)', 'COST-USD=' // trim(adjustl(cost_text))
        print '(A)', '--'
      end if
    end do
    close(u)
    print '(A,I0)', 'COUNT=', count
  end subroutine get_shipping_options

end program inventory
