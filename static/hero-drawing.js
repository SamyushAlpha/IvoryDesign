(() => {
    const drawing = document.querySelector('.hero-drawing');
    if (!drawing) return;
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    const paths = Array.from(drawing.querySelectorAll('[data-draw]'));
    const pencils = Array.from(drawing.querySelectorAll('.drawing-pencil'));
    const house = drawing.querySelector('.house-sketch');
    const reveals = Array.from(drawing.querySelectorAll('.paint-reveal'));
    const finishing = Array.from(drawing.querySelectorAll('.house-finishing'));
    const scenes = Array.from(drawing.querySelectorAll('[data-interior-scene]'));
    const sparkles = drawing.querySelector('.paint-sparkles');
    const groundShadow = drawing.querySelector('.scene-ground-shadow');
    const clamp = value => Math.min(1, Math.max(0, value));
    const ease = value => value * value * (3 - 2 * value);
    // One continuous path per stroke keeps the revealed line at the pencil tip.
    const measuredStrokes = paths.map(path => {
        const length = path.getTotalLength();
        path.style.setProperty('--stroke-length', length);
        return {path, length, scene: path.closest('[data-interior-scene]'), duration: Math.max(80, length * (path.closest('.signature-sketch') ? 3.2 : 1.9)), pencil: path.ownerSVGElement.querySelector('.drawing-pencil')};
    });
    // Each interior receives its own complete drawing timeline, then the shared
    // signature and crew sequence. Only one interior is visible at a time.
    const schedules = scenes.map(scene => {
        const strokes = measuredStrokes.filter(stroke => !stroke.scene || stroke.scene === scene).map(stroke => ({...stroke}));
        const timingScale = 54000 / strokes.reduce((sum, stroke) => sum + stroke.duration + 35, 0);
        let cursor = 350;
        strokes.forEach(stroke => {
            stroke.start = cursor;
            stroke.duration *= timingScale;
            cursor += stroke.duration + 35 * timingScale;
        });
        return strokes;
    });
    let strokes = schedules[0];
    const arrival = 55000;
    const driveDuration = 6500;
    const stepDuration = 2600;
    const walkDuration = 4800;
    const parked = arrival + driveDuration;
    const approach = parked + stepDuration;
    const hello = approach + walkDuration;
    const painting = hello + 2000;
    const goodbye = painting + 7500;
    const returning = goodbye + 2100;
    const boarding = returning + walkDuration;
    const departure = boarding + stepDuration;
    const completed = departure + driveDuration;
    const cycle = completed + 4500;
    const rides = {
        left: {parking: {x: 94, y: 600}, door: {x: 110, y: 620}, waypoints: [{x: 232, y: 620}, {x: 232, y: 548}, {x: 214, y: 506}], seat: {x: -6, y: -35}, scale: .8, facing: 1},
        right: {parking: {x: 733, y: 585}, door: {x: 749, y: 607}, waypoints: [{x: 594, y: 607}, {x: 594, y: 498}, {x: 650, y: 470}], seat: {x: -17, y: -35}, scale: .8, facing: -1},
        bottom: {parking: {x: 440, y: 658}, door: {x: 386, y: 672}, waypoints: [{x: 377, y: 672}, {x: 355, y: 629}, {x: 349, y: 590}], seat: {x: 0, y: -25}, scale: .7, facing: 1},
    };
    const vehicleElements = Array.from(drawing.querySelectorAll('.scene-vehicle'));
    const painters = Array.from(drawing.querySelectorAll('.scene-painter')).map(element => {
        const direction = element.dataset.entry;
        const vehicle = vehicleElements.find(item => item.dataset.entry === direction);
        return {
            element, direction, ride: rides[direction], vehicle,
            wheels: Array.from(vehicle.querySelectorAll('.vehicle-wheel')),
            body: vehicle.querySelector('.vehicle-body'),
            uniformBrand: element.querySelector('.uniform-brand'),
            leftShin: element.querySelector('.painter-shin-left'),
            rightShin: element.querySelector('.painter-shin-right'),
            track: vehicle.querySelector('.vehicle-track'),
            driver: vehicle.querySelector('.cab-driver'),
            driverFront: vehicle.querySelector('.cab-driver-front'),
            driverBack: vehicle.querySelector('.cab-driver-back'),
            door: vehicle.querySelector('.vehicle-door'),
            brand: vehicle.querySelector('.vehicle-brand'),
            truckFront: vehicle.querySelector('.truck-front'),
            truckRear: vehicle.querySelector('.truck-rear'),
            target: {x: Number(element.dataset.targetX), y: Number(element.dataset.targetY)},
            figure: element.querySelector('.painter-figure'),
            shadow: element.querySelector('.painter-shadow'),
            head: element.querySelector('.painter-head'),
            front: element.querySelector('.painter-head-front'),
            profile: element.querySelector('.painter-head-profile'),
            back: element.querySelector('.painter-head-back'),
            leftLeg: element.querySelector('.painter-leg-left'),
            rightLeg: element.querySelector('.painter-leg-right'),
            leftArm: element.querySelector('.painter-arm-left'),
            bucket: element.querySelector('.painter-bucket'),
            arm: element.querySelector('.painter-arm-right'),
            roller: element.querySelector('.painter-roller'),
        };
    });
    const between = (a, b, progress) => ({x: a.x + (b.x - a.x) * progress, y: a.y + (b.y - a.y) * progress});
    const vector = (a, b) => ({x: b.x - a.x, y: b.y - a.y});
    // Follow a measured path around each parked vehicle, reversing the same
    // safe route on the return journey. The head follows the current segment.
    function walkRoute(painter, progress, returning) {
        const points = [painter.ride.door, ...painter.ride.waypoints, painter.target];
        if (returning) points.reverse();
        const lengths = points.slice(1).map((point, index) => Math.hypot(point.x - points[index].x, point.y - points[index].y));
        let remaining = clamp(progress) * lengths.reduce((sum, length) => sum + length, 0);
        for (let index = 0; index < lengths.length; index++) {
            if (remaining <= lengths[index] || index === lengths.length - 1) {
                return {position: between(points[index], points[index + 1], clamp(remaining / (lengths[index] || 1))), look: vector(points[index], points[index + 1])};
            }
            remaining -= lengths[index];
        }
    }
    // Screen-edge origins remain outside the hero at every breakpoint.
    function measureEntrances() {
        const matrix = house.getScreenCTM();
        if (!matrix) return;
        const inverse = matrix.inverse();
        const bounds = drawing.getBoundingClientRect();
        painters.forEach(painter => {
            const destination = new DOMPoint(painter.ride.parking.x, painter.ride.parking.y).matrixTransform(matrix);
            const point = {
                left: new DOMPoint(bounds.left - 220, destination.y),
                right: new DOMPoint(bounds.right + 220, destination.y),
                bottom: new DOMPoint(destination.x, bounds.bottom + 220),
            }[painter.direction].matrixTransform(inverse);
            painter.origin = {x: point.x, y: point.y};
        });
    }
    let elapsed = 0;
    let previous = null;
    let frame = null;
    let visible = true;
    function paintHouse(progress) {
        reveals.forEach((rect, index) => {
            const amount = clamp(progress * 1.18 - (index % 4) * .06);
            rect.setAttribute('y', String(640 * (1 - amount)));
            rect.setAttribute('height', String(640 * amount));
        });
        finishing.forEach(item => item.setAttribute('opacity', String(clamp((progress - .65) / .35))));
    }
    function turnHead(painter, look, waving, facing) {
        const dx = look.x;
        const dy = look.y;
        const vertical = Math.abs(dy) > Math.abs(dx);
        const view = waving ? 'front' : vertical ? (dy < 0 ? 'back' : 'front') : 'profile';
        const side = dx < 0 ? -1 : 1;
        painter.front.setAttribute('opacity', view === 'front' ? '1' : '0');
        painter.profile.setAttribute('opacity', view === 'profile' ? '1' : '0');
        painter.back.setAttribute('opacity', view === 'back' ? '1' : '0');
        // Compensate for the body's mirror so the nose points toward the destination.
        painter.profile.setAttribute('transform', `scale(${side * facing} 1)`);
        const tilt = waving ? 0 : view === 'profile' ? side * facing * -6 : view === 'back' ? -5 : 4;
        painter.head.setAttribute('transform', `rotate(${tilt} 0 -73)`);
    }
    function renderPainters(time) {
        const incoming = time >= arrival && time < parked;
        const steppingDown = time >= parked && time < approach;
        const walkingIn = time >= approach && time < hello;
        const waving = (time >= hello && time < painting) || (time >= goodbye && time < returning);
        const working = time >= painting && time < goodbye;
        const walkingBack = time >= returning && time < boarding;
        const gettingOn = time >= boarding && time < departure;
        const outgoing = time >= departure && time < completed;
        const present = time >= arrival && time < completed;
        painters.forEach((painter, index) => {
            painter.element.setAttribute('opacity', present ? '1' : '0');
            painter.vehicle.setAttribute('opacity', present ? '1' : '0');
            if (!present || !painter.origin) return;
            const {ride} = painter;
            const driveIn = ease(clamp((time - arrival) / driveDuration));
            const driveOut = ease(clamp((time - departure) / driveDuration));
            // Back out along the arrival path, keeping the original vehicle heading.
            const vehiclePosition = incoming ? between(painter.origin, ride.parking, driveIn) : outgoing ? between(ride.parking, painter.origin, driveOut) : ride.parking;
            const vehicleFacing = ride.facing;
            painter.vehicle.setAttribute('transform', `translate(${vehiclePosition.x} ${vehiclePosition.y}) scale(${ride.scale} ${ride.scale})`);
            painter.body.setAttribute('transform', `scale(${vehicleFacing} 1)`);
            const distance = Math.hypot(painter.origin.x - ride.parking.x, painter.origin.y - ride.parking.y);
            const travelled = distance * (incoming ? driveIn : 1 - driveOut);
            painter.wheels.forEach(wheel => wheel.setAttribute('transform', `rotate(${travelled * 3})`));
            if (painter.track) painter.track.setAttribute('stroke-dashoffset', String(-travelled));
            if (painter.truckFront) {
                painter.truckFront.setAttribute('opacity', '0');
                painter.truckRear.setAttribute('opacity', '1');
            }
            const seat = {x: vehiclePosition.x + ride.seat.x * vehicleFacing * ride.scale, y: vehiclePosition.y + ride.seat.y * ride.scale};
            let position = painter.target;
            let riding = incoming || outgoing;
            let mount = riding ? 1 : 0;
            let look = {x: painter.direction === 'left' ? 1 : painter.direction === 'right' ? -1 : 0, y: painter.direction === 'bottom' ? -1 : -.25};
            if (incoming) { position = seat; look = vector(painter.origin, ride.parking); }
            else if (steppingDown) {
                const progress = ease(clamp(((time - parked) / stepDuration - .25) / .5));
                position = between(seat, ride.door, progress);
                position.y -= Math.sin(Math.PI * progress) * 7;
                mount = 1 - progress;
                look = vector(seat, ride.door);
            } else if (walkingIn) {
                const route = walkRoute(painter, ease(clamp((time - approach) / walkDuration)), false);
                position = route.position;
                look = route.look;
            } else if (walkingBack) {
                const route = walkRoute(painter, ease(clamp((time - returning) / walkDuration)), true);
                position = route.position;
                look = route.look;
            } else if (gettingOn) {
                const progress = ease(clamp(((time - boarding) / stepDuration - .25) / .5));
                position = between(ride.door, seat, progress);
                position.y -= Math.sin(Math.PI * progress) * 7;
                mount = progress;
                look = vector(ride.door, seat);
            } else if (outgoing) {
                position = seat;
                look = vector(ride.parking, painter.origin);
            }
            // Open first, allow time to cross the doorway, then close before driving.
            const doorPhase = steppingDown ? (time - parked) / stepDuration : gettingOn ? (time - boarding) / stepDuration : 0;
            const opening = steppingDown || gettingOn ? ease(Math.min(clamp(doorPhase / .22), clamp((1 - doorPhase) / .22))) : 0;
            const hinge = painter.door.dataset;
            painter.door.setAttribute('transform', `translate(${hinge.hingeX} ${hinge.hingeY}) skewY(${-28 * opening}) scale(${1 - .82 * opening} 1)`);
            painter.door.setAttribute('data-open', String(opening));
            // The seated artwork stays clipped inside the cab. Never draw a standing
            // character with dangling legs on top of a moving vehicle.
            painter.driver.setAttribute('opacity', String(clamp((mount - .65) / .35)));
            painter.element.setAttribute('opacity', String(clamp((1 - mount) / .35)));
            painter.driverBack.setAttribute('opacity', painter.direction === 'bottom' ? '1' : '0');
            painter.driverFront.setAttribute('opacity', painter.direction === 'bottom' ? '0' : '1');
            painter.brand.setAttribute('transform', `scale(${vehicleFacing < 0 ? -1 : 1} 1)`);
            const walking = walkingIn || walkingBack;
            const stride = Math.sin(time / 235 + index) * (walking ? 15 : 0);
            const scale = 1 - mount * .3;
            const facing = waving ? ride.facing : Math.abs(look.x) > Math.abs(look.y) ? (look.x < 0 ? -1 : 1) : ride.facing;
            painter.element.setAttribute('transform', `translate(${position.x} ${position.y}) scale(${scale})`);
            painter.element.setAttribute('data-activity', outgoing ? 'reversing' : incoming ? 'driving' : steppingDown ? 'dismounting' : gettingOn ? 'boarding' : walking ? 'walking' : waving ? 'waving' : 'painting');
            painter.vehicle.setAttribute('data-activity', outgoing ? 'reversing' : incoming ? 'driving' : 'parked');
            painter.uniformBrand.setAttribute('transform', `scale(${facing} 1)`);
            painter.leftShin.setAttribute('transform', `rotate(${walking ? Math.max(0, -stride) * 1.4 : 0} -9 -18)`);
            painter.rightShin.setAttribute('transform', `rotate(${walking ? Math.max(0, stride) * 1.4 : 0} 8 -18)`);
            painter.figure.setAttribute('transform', `translate(0 ${walking ? -Math.abs(stride) / 18 : 0}) scale(${facing} 1)`);
            turnHead(painter, look, waving, facing);
            painter.shadow.setAttribute('opacity', String((1 - mount) * .16));
            painter.leftLeg.setAttribute('transform', `rotate(${stride} -8 -35)`);
            painter.rightLeg.setAttribute('transform', `rotate(${-stride} 7 -35)`);
            painter.leftArm.setAttribute('transform', `rotate(${walking ? -stride * .45 : -mount * 35} -12 -53)`);
            const armAngle = waving ? -35 + Math.sin(time / 180 + index) * 17 : working ? -15 + Math.sin(time / 240 + index) * 32 : mount > 0 ? 55 : 8;
            painter.arm.setAttribute('transform', `rotate(${armAngle} 12 -53)`);
            painter.roller.setAttribute('opacity', waving || mount > 0 ? '0' : '1');
            painter.bucket.setAttribute('opacity', mount > 0 ? '0' : '1');
        });
        paintHouse(clamp((time - painting) / 7500));
        sparkles.setAttribute('opacity', time >= goodbye && time < completed + 1500 ? String(.55 + Math.sin(time / 260) * .35) : '0');
    }
    function render(elapsedTime) {
        const sceneIndex = Math.floor(elapsedTime / cycle) % scenes.length;
        const time = elapsedTime % cycle;
        const sceneGroundOffset = Number(scenes[sceneIndex]?.dataset.groundOffset || 0);
        groundShadow.setAttribute('opacity', String(.34 * clamp((time - 44000) / 9000)));
        scenes.forEach((scene, index) => { scene.style.display = index === sceneIndex ? '' : 'none'; });
        drawing.setAttribute('data-active-scene', String(sceneIndex));
        strokes = schedules[sceneIndex];
        pencils.forEach(pencil => pencil.setAttribute('opacity', '0'));
        strokes.forEach(stroke => {
            const progress = clamp((time - stroke.start) / stroke.duration);
            stroke.path.style.visibility = progress === 0 ? 'hidden' : 'visible';
            stroke.path.style.strokeDashoffset = stroke.length * (1 - progress);
            if (progress > 0 && progress < 1) {
                const point = stroke.path.getPointAtLength(stroke.length * progress);
                stroke.pencil.setAttribute('transform', `translate(${point.x} ${point.y + sceneGroundOffset})`);
                stroke.pencil.setAttribute('opacity', '1');
            }
        });
        renderPainters(time);
        drawing.style.opacity = time > cycle - 900 ? (cycle - time) / 900 : 1;
    }
    function tick(now) {
        if (previous !== null) elapsed += now - previous;
        previous = now;
        render(elapsed);
        frame = requestAnimationFrame(tick);
    }
    function update() {
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        previous = null;
        if (motion.matches) {
            drawing.classList.remove('is-animating');
            scenes.forEach((scene, index) => { scene.style.display = index === 0 ? '' : 'none'; });
            drawing.setAttribute('data-active-scene', '0');
            paths.forEach(path => {
                path.style.strokeDashoffset = '0';
                path.style.visibility = 'visible';
            });
            pencils.forEach(pencil => pencil.setAttribute('opacity', '0'));
            painters.forEach(painter => {
                painter.element.setAttribute('opacity', '0');
                painter.vehicle.setAttribute('opacity', '0');
            });
            sparkles.setAttribute('opacity', '0');
            paintHouse(1);
            drawing.style.opacity = 1;
        } else {
            drawing.classList.add('is-animating');
            render(elapsed);
            if (visible && !document.hidden) frame = requestAnimationFrame(tick);
        }
    }
    new ResizeObserver(measureEntrances).observe(drawing);
    new IntersectionObserver(entries => {
        visible = entries[0].isIntersecting;
        update();
    }).observe(drawing);
    document.addEventListener('visibilitychange', update);
    motion.addEventListener('change', update);
    measureEntrances();
    update();
    drawing.classList.add('is-ready');
})();
