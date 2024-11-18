
function check_nil(val,error,caption:string='');
begin
     result := val = nil;
     if result then
     ShowError(error,caption,true);
end;

Procedure test_altiumate;
Var
    prj           : IProject;
    document      : IDocument;
Begin
     document := GetWorkspace.DM_GetDocumentFromPath(document_path);
     if check_nil(document,document_path,'Opening failed') then exit;
     prj := document.DM_Project;

     if check_nil(prj,document.DM_FullPath,'No project in document') then exit;

     ShowInfo(Format('Project of %s is %s',[document_path, prj.DM_ProjectFileName]),'Test passed');
     exit;
End;

Procedure RunFromAltiumate;
Begin
     test_altiumate;
End;
