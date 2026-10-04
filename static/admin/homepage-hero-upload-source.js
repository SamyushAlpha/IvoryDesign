import { upload } from '@vercel/blob/client';

function initializeHomepageHeroUpload() {
  const form = document.querySelector('#homepagehero_form');
  if (!form || form.dataset.homepageHeroUploadReady) return;
  form.dataset.homepageHeroUploadReady = 'true';

  const uploads = [
    {
      name: 'background_image',
      folder: 'homepage/hero/images',
      accept: file => file.type.startsWith('image/'),
      error: 'Choose a valid image file.',
    },
    {
      name: 'background_video',
      folder: 'homepage/hero/videos',
      accept: file => ['video/mp4', 'video/webm'].includes(file.type)
        || /\.(mp4|webm)$/i.test(file.name),
      error: 'Choose an MP4 or WebM video.',
    },
  ].map(({ name, ...uploadOptions }) => ({
    ...uploadOptions,
    chooser: form.querySelector(`input[name="${name}_upload"]`),
    urlInput: form.querySelector(`input[name="${name}"]`),
  }));

  let uploaded = false;
  form.addEventListener('submit', async event => {
    const selected = uploads.filter(({ chooser }) => chooser?.files?.[0]);
    if (uploaded || !selected.length) return;
    event.preventDefault();
    const submitter = event.submitter;
    const buttons = [...form.querySelectorAll('input[type="submit"], button[type="submit"]')];
    buttons.forEach(button => button.disabled = true);

    try {
      for (const { chooser, urlInput, folder, accept, error } of selected) {
        const file = chooser.files[0];
        if (!accept(file)) throw new Error(error);
        if (folder.endsWith('/videos') && file.size > 200 * 1024 * 1024) {
          throw new Error('The video must be 200 MB or smaller.');
        }
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
      alert(error?.message || 'The homepage background could not be uploaded. Please try again.');
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeHomepageHeroUpload, { once: true });
} else {
  initializeHomepageHeroUpload();
}
