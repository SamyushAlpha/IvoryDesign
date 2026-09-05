import { upload } from '@vercel/blob/client';

function initializePortfolioPdfUpload() {
  const form = document.querySelector('form[method="post"]');
  if (!form || form.dataset.pdfUploadReady) return;
  form.dataset.pdfUploadReady = 'true';
  const pending = [];
  function enhance(urlInput) {
    if (urlInput.dataset.pdfChooserReady) return;
    urlInput.dataset.pdfChooserReady = 'true';
    urlInput.type = 'hidden';
    const chooserName = urlInput.name.replace(/portfolio_pdf$/, 'portfolio_pdf_upload');
    let chooser = form.querySelector(`input[name="${CSS.escape(chooserName)}"]`);
    if (!chooser) {
      chooser = document.createElement('input');
      chooser.type = 'file'; chooser.accept = 'application/pdf,.pdf'; chooser.className = 'vTextField';
      chooser.setAttribute('aria-label', 'Choose portfolio PDF');
      urlInput.insertAdjacentElement('afterend', chooser);
    }
    if (urlInput.value) {
      const current = document.createElement('a');
      current.href = urlInput.value; current.target = '_blank'; current.rel = 'noopener';
      current.textContent = 'View current PDF'; current.style.marginLeft = '12px';
      chooser.insertAdjacentElement('afterend', current);
    }
    pending.push({ urlInput, chooser });
  }
  form.querySelectorAll('input[name="portfolio_pdf"], input[name$="-portfolio_pdf"]').forEach(enhance);
  new MutationObserver(() => {
    form.querySelectorAll('input[name="portfolio_pdf"], input[name$="-portfolio_pdf"]').forEach(enhance);
  }).observe(form, { childList: true, subtree: true });
  let uploaded = false;
  form.addEventListener('submit', async (event) => {
    const selected = pending.filter(({ chooser }) => chooser.files?.[0]);
    if (uploaded || !selected.length) return;
    event.preventDefault();
    const submitter = event.submitter;
    const buttons = [...form.querySelectorAll('input[type="submit"], button[type="submit"]')];
    buttons.forEach(button => button.disabled = true);
    try {
      for (const { urlInput, chooser } of selected) {
        const file = chooser.files[0];
        if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) throw new Error('Choose a PDF file.');
        const blob = await upload(`team/portfolio/pdfs/${file.name}`, file, {
          access: 'public', handleUploadUrl: '/api/blob-upload', multipart: file.size > 10 * 1024 * 1024,
        });
        urlInput.value = blob.url;
        chooser.value = '';
      }
      uploaded = true;
      buttons.forEach(button => button.disabled = false);
      form.requestSubmit(submitter || undefined);
    } catch (error) {
      buttons.forEach(button => button.disabled = false);
      alert(error?.message || 'The PDF could not be uploaded. Please try again.');
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializePortfolioPdfUpload, { once: true });
} else {
  initializePortfolioPdfUpload();
}
