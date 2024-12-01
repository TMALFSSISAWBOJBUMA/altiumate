function check_val(val, expected_val, error_msg: string, caption: string = '');
begin
  result := val = expected_val;
  if result then
    ShowError(error_msg, caption, true);
end;

function string_after_char(input: string, delimiter: char): string;
// get substring after last $delim character in $str
var
  cut_idx: cardinal;
begin
  cut_idx := length(input);
  while (cut_idx > 0) and (input[cut_idx] <> delimiter) do
    dec(cut_idx);
  if cut_idx = 0 then
    result := ''
  else
    result := copy(input, cut_idx + 1, length(input) - cut_idx + 1);
end;

Procedure test_altiumate;
Begin
  ShowInfo(ReplaceStr(passed_files, ',', #13#10),
    'Files passed to altiumate run');
  return_code := 0;
End;

procedure run_test;
const
  paf = 'C:\Git\Solarowy gitlab\HW\lstesc-controlpcb\ESC_Control.PrjPcb';
begin
  outjob_run_all(paf);
end;
