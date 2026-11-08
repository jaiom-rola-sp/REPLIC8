program Payroll;
{ Gross pay: hours from the command line times a fixed rate. }
var
  hours, code: Integer;
begin
  if ParamCount < 1 then Halt(1);
  Val(ParamStr(1), hours, code);
  WriteLn('gross=', hours * 20);
end.
