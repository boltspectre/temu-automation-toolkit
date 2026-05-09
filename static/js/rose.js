(function () {
  // 如果已经存在，则不重复创建
  if (document.getElementById('rose-petal-canvas')) return;

  const canvas = document.createElement('canvas');
  canvas.id = 'rose-petal-canvas';
  canvas.style.position = 'fixed';
  canvas.style.top = '0';
  canvas.style.left = '0';
  canvas.style.pointerEvents = 'none'; // 不影响页面交互
  canvas.style.zIndex = '9999';
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  let width = window.innerWidth;
  let height = window.innerHeight;
  canvas.width = width;
  canvas.height = height;

  // 调整窗口大小时重置画布
  window.addEventListener('resize', () => {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
  });

  // 玫瑰花瓣路径（简化但唯美的心形+花瓣轮廓）
  function drawPetal(ctx, x, y, scale, rotation) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rotation);
    ctx.scale(scale, scale);

    ctx.beginPath();
    ctx.moveTo(0, -8);
    ctx.bezierCurveTo(6, -12, 10, -4, 6, 4);
    ctx.bezierCurveTo(2, 8, -2, 8, -6, 4);
    ctx.bezierCurveTo(-10, -4, -6, -12, 0, -8);
    ctx.closePath();

    // 渐变色：深红到粉红
    const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, 10);
    gradient.addColorStop(0, 'rgba(220, 20, 60, 0.9)');
    gradient.addColorStop(1, 'rgba(255, 105, 180, 0.7)');
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.restore();
  }

  // 花瓣对象
  class Petal {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * width + 100; // 从右侧外开始
      this.y = -20;
      this.scale = 0.5 + Math.random() * 0.7;
      this.rotation = Math.random() * Math.PI * 2;
      this.rotationSpeed = (Math.random() - 0.5) * 0.03;
      this.speedY = 1 + Math.random() * 2;
      this.speedX = -(1 + Math.random() * 1.5); // 向左飘（负值）
      this.opacity = 0.7 + Math.random() * 0.3;
    }

    update() {
      this.y += this.speedY;
      this.x += this.speedX;
      this.rotation += this.rotationSpeed;

      // 若花瓣飘出屏幕底部或左侧太远，重置
      if (this.y > height + 30 || this.x < -50) {
        this.reset();
      }
    }

    draw() {
      ctx.globalAlpha = this.opacity;
      drawPetal(ctx, this.x, this.y, this.scale, this.rotation);
    }
  }

  const petals = [];
  const petalCount = Math.min(80, Math.floor(width / 20)); // 根据屏幕宽度调整数量

  for (let i = 0; i < petalCount; i++) {
    petals.push(new Petal());
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    petals.forEach(petal => {
      petal.update();
      petal.draw();
    });

    requestAnimationFrame(animate);
  }

  animate();
})();