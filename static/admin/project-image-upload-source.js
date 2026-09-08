import { upload } from '@vercel/blob/client';

function initializeProjectImageUpload() {
  const form = document.querySelector('form[method="post"]');
  if (!form || form.dataset.projectImageUploadReady) return;
  form.dataset.projectImageUploadReady = 'true';

  function pairs() {
    return [...form.querySelectorAll('input[type="file"][name="image_upload"], input[type="file"][name$="-image_upload"]')]
      .map(chooser => {
        const urlName = chooser.name.replace(/image_upload$/, 'image');
        return { chooser, urlInput: form.querySelector(`input[name="${CSS.escape(urlName)}"]`) };
      })
      .filter(pair => pair.urlInput);
  }

  let uploaded = false;
  form.addEventListener('submit', async event => {
    const selected = pairs().filter(({ chooser }) => chooser.files?.[0]);
    if (uploaded || !selected.length) return;
    event.preventDefault();
    const submitter = event.submitter;
    const buttons = [...form.querySelectorAll('input[type="submit"], button[type="submit"]')];
    buttons.forEach(button => button.disabled = true);
    try {
      for (const { chooser, urlInput } of selected) {
        const file = chooser.files[0];
        if (!file.type.startsWith('image/')) throw new Error('Choose an image file.');
        const gallery = chooser.name !== 'image_upload';
        const folder = gallery ? 'projects/gallery' : 'projects/covers';
        const blob = await upload(`${folder}/${file.name}`, file, {
          access: 'public',
          handleUploadUrl: '/api/blob-upload',
          multipart: file.size > 10 * 1024 * 1024,
        });
        urlInput.value = blob.url;
        chooser.value = '';
      }
      uploaded = true;
      buttons.forEach(button => button.disabled = false);
      form.requestSubmit(submitter || undefined);
    } catch (error) {
      buttons.forEach(button => button.disabled = false);
      alert(error?.message || 'The project image could not be uploaded. Please try again.');
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeProjectImageUpload, { once: true });
} else {
  initializeProjectImageUpload();
}
