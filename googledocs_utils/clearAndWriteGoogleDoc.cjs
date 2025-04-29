const { configGoogleDoc } = require('./configGoogleDoc.cjs');

async function clearAndWriteGoogleDoc(documentId, markdownText) {
  const google = await configGoogleDoc();
  const docs = google.docs;

  try {
    // Get document's current length
    const document = await docs.documents.get({ documentId });
    const documentLength = document.data.body.content.length;

    // Clear existing content if necessary
    if (documentLength > 1) {
      const startIndex = 1;
      const endIndex = document.data.body.content[document.data.body.content.length - 1].endIndex;
      
      if (endIndex - startIndex > 1) {
        await docs.documents.batchUpdate({
          documentId,
          requestBody: {
            requests: [{
              deleteContentRange: {
                range: {
                  startIndex: 1,
                  endIndex: endIndex - 1,
                }
              }
            }]
          }
        });
      }
    }

    // Process the text and create formatting requests
    const requests = [];
    let currentIndex = 1;

    // Split text into lines and process each one
    const lines = markdownText.split('\n');
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i].trim();
      if (!line) {
        requests.push({
          insertText: {
            location: { index: currentIndex },
            text: '\n'
          }
        });
        currentIndex++;
        continue;
      }

      // Handle headings
      if (line.startsWith('## ')) {
        const headingText = line.substring(3);
        requests.push({
          insertText: {
            location: { index: currentIndex },
            text: headingText + '\n'
          }
        });

        // Apply heading style
        requests.push({
          updateParagraphStyle: {
            range: {
              startIndex: currentIndex,
              endIndex: currentIndex + headingText.length
            },
            paragraphStyle: {
              namedStyleType: 'HEADING_2',
              spaceAbove: { magnitude: 20, unit: 'PT' },
              spaceBelow: { magnitude: 10, unit: 'PT' }
            },
            fields: 'namedStyleType,spaceAbove,spaceBelow'
          }
        });

        // Make the heading bold and set font size
        requests.push({
          updateTextStyle: {
            range: {
              startIndex: currentIndex,
              endIndex: currentIndex + headingText.length
            },
            textStyle: {
              bold: true,
              fontSize: { magnitude: 20, unit: 'PT' }
            },
            fields: 'bold,fontSize'
          }
        });

        currentIndex += headingText.length + 1;
        continue;
      }

      // Handle bullet points
      if (line.startsWith('* ')) {
        line = line.substring(2);
        
        // Handle nested bullets by adjusting the text
        if (line.startsWith('    ')) {
          line = '    ' + line.trim();
        }

        // Remove markdown bold syntax
        line = line.replace(/\*\*(.*?)\*\*/g, '$1');
        
        requests.push({
          insertText: {
            location: { index: currentIndex },
            text: line + '\n'
          }
        });

        // Apply bullet style
        requests.push({
          createParagraphBullets: {
            range: {
              startIndex: currentIndex,
              endIndex: currentIndex + line.length
            },
            bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
          }
        });

        // Find bold sections and apply bold formatting
        const boldRegex = /\*\*(.*?)\*\*/g;
        let match;
        let originalLine = lines[i];
        while ((match = boldRegex.exec(originalLine)) !== null) {
          const boldText = match[1];
          const startPos = line.indexOf(boldText);
          if (startPos !== -1) {
            requests.push({
              updateTextStyle: {
                range: {
                  startIndex: currentIndex + startPos,
                  endIndex: currentIndex + startPos + boldText.length
                },
                textStyle: { bold: true },
                fields: 'bold'
              }
            });
          }
        }

        currentIndex += line.length + 1;
        continue;
      }

      // Handle regular paragraphs
      // Remove markdown bold syntax while keeping the text
      line = line.replace(/\*\*(.*?)\*\*/g, '$1');
      
      requests.push({
        insertText: {
          location: { index: currentIndex },
          text: line + '\n'
        }
      });

      // Find and apply bold formatting
      const boldRegex = /\*\*(.*?)\*\*/g;
      let match;
      let originalLine = lines[i];
      while ((match = boldRegex.exec(originalLine)) !== null) {
        const boldText = match[1];
        const startPos = line.indexOf(boldText);
        if (startPos !== -1) {
          requests.push({
            updateTextStyle: {
              range: {
                startIndex: currentIndex + startPos,
                endIndex: currentIndex + startPos + boldText.length
              },
              textStyle: { bold: true },
              fields: 'bold'
            }
          });
        }
      }

      currentIndex += line.length + 1;
    }

    // Apply all changes in a single batch update
    if (requests.length > 0) {
      await docs.documents.batchUpdate({
        documentId,
        requestBody: { requests }
      });
    }

    console.log('Document updated successfully');
    return true;
  } catch (err) {
    console.error('Error modifying document:', err);
    throw err;
  }
}

module.exports = { clearAndWriteGoogleDoc };