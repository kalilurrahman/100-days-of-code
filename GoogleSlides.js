function generateGoogleSlidesFromGoogleSheets() {
  var dataSSURL = // INCLUDE YOUR FILE HERE with /edit"
    var ss = SpreadsheetApp.openByUrl(dataSSURL);
  var googleDeck = SlidesApp.getActivePresentation();
  var reportTemplate = // INCLUDE YOUR Google Slides TemplateFILE ID like 1QzgQz3dR1216tKq1J1ZnhE8vd1hqxGS3OAE73L_XPMQANDH"
  
  var sheet = ss.getSheetByName('QuotesPg');
  
  var dataRange = sheet.getDataRange();
  var numRows = dataRange.getNumRows();

  var values = sheet.getRange('A1:E10').getValues();
  Logger.log(values);

  var slides = googleDeck.getSlides();
  var templateSlide = slides[1];
  var presLength = slides.length;
  
  values.forEach(function(page){
    if(page[0]){
      qqtitle = page[0];
      qqname =page[1];
      qqauthor = page[2];
      qqtopic = page[3];
      qqquote = page[4];
      templateSlide.duplicate();
      slides = googleDeck.getSlides();
      newSlide = slides[2];
      var shapes = (newSlide.getShapes());
        shapes.forEach(function(shape){
         shape.getText().replaceAllText('{{Author}}',qqauthor);
         shape.getText().replaceAllText('{{Topic}}',qqtopic);
         shape.getText().replaceAllText('{{Quote}}',qqquote);
        });
      presLength = slides.length;
      newSlide.move(presLength);
    }
   });
  
//  templateSlide.remove();
  introSlide = slides[0];
  introSlide_(introSlide, slides, qqtitle, qqname);  
  copyReportTemplate_(reportTemplate); 
}
               

function copyReportTemplate_(reportTemplate) {
  var date = Utilities.formatDate(new Date(), 'GMT+1', 'MM-yyyy');
  var title = 'Quotes of the Day' + ' By Kalilur ' + '-' + date;
  var template = DriveApp.getFileById(reportTemplate);
  var driveResponse = template.makeCopy(title);
  return driveResponse.getId();
}

function introSlide_(slide, presentation, qqtitle,qqname) {
  slide.replaceAllText('{{Title}}', qqtitle);
  slide.replaceAllText('{{Name}}', qqname);
  var date = Utilities.formatDate(new Date(), 'GMT+1', 'yyyy-MM-dd');
  slide.replaceAllText('{{Date}}', date);
}

