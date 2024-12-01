const
  passed_files = '';

Var
  return_code: integer;

Procedure RunFromAltiumate;
Var
  tmp_file: TextFile;
Begin
  return_code := 1;
  AssignFile(tmp_file, 'C:/Git/altiumate/altiumate/AD_out');
  Try
    test_altiumate;
  Finally
    ReWrite(tmp_file);
    WriteLn(tmp_file, return_code);
    CloseFile(tmp_file);
  end;

End;
