(function () {
  function initDestinationMultiUpload() {
    var fileInput = document.getElementById('id_new_images');
    var primaryIndexInput = document.getElementById('id_primary_new_image_index');

    if (!fileInput || !primaryIndexInput) {
      return;
    }

    var existingPreview = document.getElementById('destination-multi-upload-preview');
    if (existingPreview) {
      existingPreview.remove();
    }

    var wrapper = document.createElement('div');
    wrapper.id = 'destination-multi-upload-preview';
    wrapper.style.marginTop = '10px';

    var helper = document.createElement('p');
    helper.style.margin = '0 0 8px';
    helper.style.fontSize = '12px';
    helper.style.color = '#5f6368';
    helper.textContent = 'New image preview (choose one as cover):';

    var grid = document.createElement('div');
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(130px, 1fr))';
    grid.style.gap = '8px';

    wrapper.appendChild(helper);
    wrapper.appendChild(grid);
    fileInput.parentNode.appendChild(wrapper);

    function renderPreview() {
      grid.innerHTML = '';

      var files = Array.prototype.slice.call(fileInput.files || []);
      if (!files.length) {
        primaryIndexInput.value = '';
        return;
      }

      var currentPrimary = Number(primaryIndexInput.value);
      if (Number.isNaN(currentPrimary) || currentPrimary < 0 || currentPrimary >= files.length) {
        currentPrimary = 0;
      }
      primaryIndexInput.value = String(currentPrimary);

      files.forEach(function (file, index) {
        if (!file.type || file.type.indexOf('image/') !== 0) {
          return;
        }

        var card = document.createElement('label');
        card.style.display = 'block';
        card.style.border = '1px solid #d0d7de';
        card.style.borderRadius = '6px';
        card.style.padding = '6px';
        card.style.background = '#fff';
        card.style.cursor = 'pointer';

        var image = document.createElement('img');
        image.src = URL.createObjectURL(file);
        image.alt = file.name;
        image.style.width = '100%';
        image.style.height = '80px';
        image.style.objectFit = 'cover';
        image.style.borderRadius = '4px';
        image.onload = function () {
          URL.revokeObjectURL(image.src);
        };

        var caption = document.createElement('div');
        caption.style.marginTop = '4px';
        caption.style.fontSize = '11px';
        caption.style.color = '#57606a';
        caption.style.whiteSpace = 'nowrap';
        caption.style.overflow = 'hidden';
        caption.style.textOverflow = 'ellipsis';
        caption.textContent = file.name;

        var radioWrap = document.createElement('div');
        radioWrap.style.display = 'flex';
        radioWrap.style.alignItems = 'center';
        radioWrap.style.gap = '4px';
        radioWrap.style.marginTop = '4px';

        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'destination_primary_new_radio';
        radio.value = String(index);
        radio.checked = index === currentPrimary;
        radio.addEventListener('change', function () {
          primaryIndexInput.value = radio.value;
        });

        var radioLabel = document.createElement('span');
        radioLabel.style.fontSize = '11px';
        radioLabel.textContent = 'Set as cover';

        radioWrap.appendChild(radio);
        radioWrap.appendChild(radioLabel);

        card.appendChild(image);
        card.appendChild(caption);
        card.appendChild(radioWrap);
        grid.appendChild(card);
      });
    }

    fileInput.addEventListener('change', renderPreview);
    renderPreview();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDestinationMultiUpload);
  } else {
    initDestinationMultiUpload();
  }
})();
